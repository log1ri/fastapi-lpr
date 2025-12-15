import cv2
import base64
import logging
import numpy as np
import time
from datetime import datetime
from ultralytics import YOLO
from app.services.ocr_labelMapping import label_dict, province_map

class OCRServiceError(Exception):
    """Custom error for OCR service failures."""
    pass

logger = logging.getLogger("ocr_service") 
class OCRService:
       

    def __init__(self):
        try:

            logger.info("==============================================") 
            logger.info("✅ Initializing OCR Service")

            # print("\n" + "=" * 60)
            # print("✅  OCR Service Initialized")
            # print("🔎  Plate Model   : ./model/yolo/best_license_plate_detect.pt")
            # print("🔤  OCR Model     : ./model/yolo/best_license_plate_recognition.pt")
            # print("=" * 60 + "\n")
            logger.info("🔎 Loading plate model from: %s", "./model/yolo/best_license_plate_detect.pt")
            self.plate_model = YOLO("./model/yolo/best_license_plate_detect.pt")  
            
            logger.info("🔤 Loading OCR model from:   %s", "./model/yolo/best_license_plate_recognition.pt")
            self.ocr_model = YOLO("./model/yolo/best_license_plate_recognition.pt") 
        
            logger.info("✅ OCR Service initialized successfully")
            logger.info("=============================================="+"\n") 
        except Exception as e:
            print(f"Error initializing OCR Service: {e}")
            raise OCRServiceError(f"Failed to initialize OCR models: {e}")

    def resize_image(self, image: np.ndarray, target_size=(640, 640)) -> np.ndarray:
        return cv2.resize(image, target_size)
    
    def img_to_jpeg_bytes(self, img: np.ndarray) -> bytes:
        ok, buf = cv2.imencode(".jpg", img)
        if not ok:
            return b""
        return buf.tobytes()

    # 1
    def decode_base64(self, img_base64: str) -> bytes | None:
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
    def preProcess(self, img_bytes: bytes) -> tuple[np.ndarray, np.ndarray] | None:
        """
        Change raw image bytes to numpy array (BGR) for OpenCV/YOLO usage.
        """
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        
        resized = self.resize_image(frame, target_size=(640, 640))
        return frame, resized
    
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
    
    # 4
    def crop_plate(self, resized_decoded: np.ndarray, plate_boxes) -> tuple[np.ndarray, np.ndarray] | None:
        
        x1, y1, x2, y2 = map(int, plate_boxes.xyxy[0])
        cropped_plate = resized_decoded[y1:y2, x1:x2]
        
        cv2.imwrite("debug_cropped_plate.jpg", cropped_plate)
        
        resized_cropped_plate = self.resize_image(cropped_plate, target_size=(640, 640))
        return cropped_plate, resized_cropped_plate
    
    # 5
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
    
    # 6
    def build_detections(self, boxes) -> list[dict]:
        # get class ids and x/y centers
        cls_list = boxes.cls.cpu().numpy()
        xywh = boxes.xywh.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        
        x_centers = xywh[:, 0]
        y_centers = xywh[:, 1]
        heights = xywh[:, 3]

        # print("Classes:", cls_list)
        # print("Conf  :", confs)

        # print("X Centers:", x_centers)
        # print("Y Centers:", y_centers)
        # print("Heights:", heights)

        # create list of detections with [[ name, x_center, y_center, height ], ...]
        detections: list[dict] = []
        for i, cls_id in enumerate(cls_list):
            detections.append({
                "name": self.ocr_model.names[int(cls_id)],
                "x": float(x_centers[i]),
                "y": float(y_centers[i]),
                "h": float(heights[i]),
                "conf": float(confs[i]),
            })
        return detections

    # 7
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
    
    # 8
    def decode_plate_text(self, sorted_detections: list[dict]) -> dict:
        decoded = ""
        province = ""

        final_list = [(d["name"], d["x"], d["conf"]) for d in sorted_detections]
        confs_for_text: list[float] = [] 
        
        for name, _, conf in final_list:
            if name in province_map:
                province = label_dict.get(name, f"[{name}]")
            else:
                decoded += label_dict.get(name, f"[{name}]")
                confs_for_text.append(conf)

        if confs_for_text:
            avg_conf = sum(confs_for_text) / len(confs_for_text)
        else:
            avg_conf = 0.0
        
        logger.info("Decoded Text:", decoded)
        logger.info("Province:", province)
        logger.info("Avg Confidence:", avg_conf)

        return {"regNum": decoded, "Province": province, "confidence": avg_conf}
    
    def predict(self, img_base64: str,organize: str | None = None) -> dict:
        try:
            start_time = time.time()
            # 1 decode base64 image =======================================
            decoded = self.decode_base64(img_base64)
            logger.info("Base64 decoding done.")
            if decoded is None:
                logger.error("[OCR] invalid_image: base64 decode failed")
                # decoding failed ใช้งานได้
                return {
                    "error": "Invalid base64 image",
                    "regNum": None,
                    "province": None,
                    "confidence": 0.0,
                    "readStatus": "invalid_image",
                    "originalImage": None,
                    "croppedPlateImage": None,
                    "latencyMs": (time.time() - start_time) * 1000

                }
            
            # ===========================================================
            
            
            # pre-process image =========================================
            pre = self.preProcess(decoded)
            logger.info("Pre-processing done.")
            if pre is None:
                logger.error("[OCR] invalid_image: cv2.imdecode failed (unsupported format?)")
                # pre-processing failed (cannot decode(cv) image) ใช้งานได้
                return {
                    "error": "Cannot decode image(cv)",
                    "regNum": None,
                    "province": None,
                    "confidence": 0.0,
                    "readStatus": "invalid_image",
                    "originalImage": None,
                    "croppedPlateImage": None,
                    "latencyMs": (time.time() - start_time) * 1000
                }
            original_frame, resized_decoded = pre
            cv2.imwrite("debug_preprocessed.jpg", resized_decoded)
            # ===========================================================


            # detect plate ==============================================
            plate_boxes = self.detect_plate(resized_decoded)
            logger.info("Plate detection done.")
            if plate_boxes is None:
                logger.error("[OCR] no_plate: YOLO plate detector found nothing")
                # no plate detected return error with original image --> issuelog ใช้งานได้
                return {
                    "error": "No plate detected",
                    "regNum": None,
                    "province": None,
                    "confidence": 0.0,
                    "readStatus": "no_plate",   
                    "originalImage": self.img_to_jpeg_bytes(original_frame),
                    "croppedPlateImage": None,
                    "latencyMs": (time.time() - start_time) * 1000
                }
            # ===========================================================

            
            # ************************************************
            # 3. crop plate image and resize ============================
            cropped_plate, resized_cropped_plate = self.crop_plate(resized_decoded, plate_boxes)

            boxes = self.run_ocr_model(resized_cropped_plate)
            logger.info("Char detection done.")

            if boxes is None:
                print("[OCR] no_text: OCR model found no characters")
                # Plate detected but no text found ใช้งานได้
                return {
                    "error": "No text detected",
                    "regNum": None,
                    "province": None,
                    "confidence": 0.0,
                    "readStatus": "no_text",  # อ่านไม่ออกเลย
                    # "originalImage": self.img_to_jpeg_bytes(original_frame),
                    # "croppedPlateImage": self.img_to_jpeg_bytes(cropped_plate),
                    "originalImage": None,
                    "croppedPlateImage": self.img_to_jpeg_bytes(cropped_plate),
                    "latencyMs": (time.time() - start_time) * 1000
                }
            # ===========================================================
            
            # extract boxes and classes
            detections = self.build_detections(boxes)
            logger.info("extract boxes and classes done.")


            # sort by y center first
            sorted_detections = self.group_and_sort_detections(detections)
            logger.info("Sort by y center done.")
            
            # decode plate text
            result = self.decode_plate_text(sorted_detections)
            logger.info("Decode plate text done.")

            # format output images
            original_img = self.img_to_jpeg_bytes(original_frame)
            crop_img = self.img_to_jpeg_bytes(cropped_plate)
            
            return {
                "error": None,
                "regNum": result["regNum"],
                "province": result["Province"],
                "confidence": result["confidence"],
                "readStatus": 'complete' ,
                "originalImage": original_img,
                "croppedPlateImage": crop_img,
                "latencyMs": (time.time() - start_time) * 1000
            }
        except Exception as e:
            logger.error(f"Error in OCR prediction: {e}")
            return {
                "error": f"OCR prediction failed: {e}",
                "regNum": None,
                "province": None,
                "confidence": 0.0,
                "readStatus": "error",
                "originalImage": None,
                "croppedPlateImage": None,
                "latencyMs": (time.time() - start_time) * 1000
            }
        