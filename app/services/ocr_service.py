import cv2
import base64
import numpy as np
from ultralytics import YOLO
from app.services.ocr_labelMapping import label_dict, province_map



class OCRService:
       

    def __init__(self):
        try:
            print("\n" + "=" * 60)
            print("✅  OCR Service Initialized")
            print("🔎  Plate Model   : ./model/yolo/best_license_plate_detect.pt")
            print("🔤  OCR Model     : ./model/yolo/best_license_plate_recognition.pt")
            print("=" * 60 + "\n")
            
            self.plate_model = YOLO("./model/yolo/best_license_plate_detect.pt")  
            self.ocr_model = YOLO("./model/yolo/best_license_plate_recognition.pt")  
        except Exception as e:
            print(f"Error initializing OCR Service: {e}")

    def resize_image(self, image: np.ndarray, target_size=(640, 640)) -> np.ndarray:
        return cv2.resize(image, target_size)

    # 1
    def decode_base64(self, img_base64: str) -> bytes:
        try:
            
            # cut prefix (data:image/jpeg;base64,)
            if "," in img_base64:
                img_base64 = img_base64.split(",")[1]
                
            # decode base64 (raw bytes)
            imgData = base64.b64decode(img_base64)
                       
            return imgData
        
        except Exception as e:
            print(f"Error decoding base64 image: {e}")
            return None
    
    # 2
    def preProcess(self, img_bytes: bytes) -> np.ndarray:
        """
        Change raw image bytes to numpy array (BGR) for OpenCV/YOLO usage.
        """
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        
        return self.resize_image(frame, target_size=(640, 640))
    
    # 3
    def detect_plate(self, img: np.ndarray):
        plate_results = self.plate_model.predict(
            img, conf=0.5, 
            save=False, 
            verbose=False,
        )
        
        boxes = plate_results[0].boxes
        if boxes is None or len(boxes) == 0:
            return None
        return boxes
    
    def crop_plate(self, resized_decoded: np.ndarray, plate_boxes) -> np.ndarray:
        
        x1, y1, x2, y2 = map(int, plate_boxes.xyxy[0])
        cropped_plate = resized_decoded[y1:y2, x1:x2]
        cv2.imwrite("debug_cropped_plate.jpg", cropped_plate)
        resized_cropped_plate = self.resize_image(cropped_plate, target_size=(640, 640))
        return resized_cropped_plate
    
    def run_ocr_model(self, plate_img: np.ndarray):
        results = self.ocr_model.predict(
            plate_img, 
            conf=0.7, 
            save=False, 
            save_txt=False, 
            verbose=False
        )
        
        boxes = results[0].boxes
        if boxes is None or boxes.cls is None or len(boxes) == 0:
            return None
        return boxes
    
    def build_detections(self, boxes) -> list[dict]:
        # get class ids and x/y centers
        cls_list = boxes.cls.cpu().numpy()
        xywh = boxes.xywh.cpu().numpy()
        x_centers = xywh[:, 0]
        y_centers = xywh[:, 1]
        heights = xywh[:, 3]

        print("Classes:", cls_list)
        print("X Centers:", x_centers)
        print("Y Centers:", y_centers)
        print("Heights:", heights)

        # create list of detections with [[ name, x_center, y_center, height ], ...]
        detections: list[dict] = []
        for i, cls_id in enumerate(cls_list):
            detections.append({
                "name": self.ocr_model.names[int(cls_id)],
                "x": float(x_centers[i]),
                "y": float(y_centers[i]),
                "h": float(heights[i]),
            })
        return detections

    def group_and_sort_detections(self, detections: list[dict]) -> list[dict]:
        # sort by Y center 
        detections.sort(key=lambda k: k["y"])
        print("Sorted Detections by Y:", detections)

        sorted_detections: list[dict] = []
        current_line: list[dict] = []

        if not detections:
            return sorted_detections

        # First detection starts the first line
        current_line.append(detections[0])

        for det in detections[1:]:
            prev = current_line[-1]
            
            # Calculate the difference in Y-axis between the current detection and the last one in the line
            y_diff = abs(det["y"] - prev["y"])
            
            # Use average height to set a threshold (if Y difference is within 50% of height, consider it the same line)
            threshold = max(det["h"], prev["h"]) * 0.5

            if y_diff < threshold:
                # same line: add to temporary list
                current_line.append(det)
            else:
                # New line: 
                # A. Sort the old line by X-axis (left to right)
                current_line.sort(key=lambda k: k["x"])   
                # B. Save the results
                sorted_detections.extend(current_line)
                # C. Start a new line
                current_line = [det]

        # last line Don't forget to save the last set (bottom line)
        if current_line:
            current_line.sort(key=lambda k: k["x"])
            sorted_detections.extend(current_line)

        return sorted_detections
    
    def decode_plate_text(self, sorted_detections: list[dict]) -> dict:
        decoded = ""
        province = ""

        final_list = [(d["name"], d["x"]) for d in sorted_detections]

        for name, _ in final_list:
            if name in province_map:
                province = label_dict.get(name, f"[{name}]")
            else:
                decoded += label_dict.get(name, f"[{name}]")

        print("Decoded Text:", decoded)
        print("Province:", province)

        return {"regNum": decoded, "Province": province}
    
    def predict(self, img_base64: str) -> dict:
        try:
            # decode base64 image =======================================
            decoded = self.decode_base64(img_base64)

            if decoded is None:
                return {"error": "Invalid base64 image"}
            
            # ===========================================================
            
            
            # pre-process image =========================================
            resized_decoded = self.preProcess(decoded)
            
            if resized_decoded is None:
                return {"error": "Cannot decode image"}
            
            cv2.imwrite("debug_preprocessed.jpg", resized_decoded)
            # ===========================================================


            # detect plate ==============================================
            plate_boxes = self.detect_plate(resized_decoded)
            
            if plate_boxes is None :
                return {"error": "No plate detected"}
            # ===========================================================

            # 3. crop plate image and resize ============================
            resized_cropped_plate = self.crop_plate(resized_decoded, plate_boxes)

            boxes = self.run_ocr_model(resized_cropped_plate)
            if boxes is None:
                return {"error": "No text detected"}
            # ===========================================================
            
            # extract boxes and classes
            detections = self.build_detections(boxes)

            # sort by y center first
            sorted_detections = self.group_and_sort_detections(detections)

            # decode plate text
            res = self.decode_plate_text(sorted_detections)
            return res
        except Exception as e:
            print(f"Error in OCR prediction: {e}")
            return {"error": f"OCR prediction failed: {e}"}
        