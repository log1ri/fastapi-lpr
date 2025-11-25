import base64
from PIL import Image
import numpy as np
import io
import cv2
from ultralytics import YOLO
from app.services.ocr_labelMapping import label_dict, province_map
from operator import itemgetter


class OCRService:
       

    def __init__(self):
        print("OCR Service Initialized")
    
    def predict(self, img_base64: str) -> dict:
        try:
            # decode base64 image
            decoded = self.decode_base64(img_base64)
            
            if decoded == "Decode Base64 error" or decoded is None:
                return {"error": "Invalid base64 image"}
            
            # convert raw bytes to numpy array
            nparr = np.frombuffer(decoded, np.uint8)
            
            # decode image
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            resized = cv2.resize(frame, (512, 512))
            model = YOLO("./model/yolo/best.pt")
            results = model.predict(resized , conf=0.6, save=False, save_txt=False, verbose=False)
            
            # extract boxes and classes
            boxes = results[0].boxes
            
            if boxes is None or boxes.cls is None:
                return {"error": "No text detected"}
            
            # get class ids and x centers
            cls_list   = boxes.cls.cpu().numpy()
            x_centers  = boxes.xywh[:, 0].cpu().numpy()
            
            # sort by x center
            detections = [(model.names[int(c)], float(x)) for c, x in zip(cls_list, x_centers)]
            sorted_detections = sorted(detections, key=itemgetter(1))
            
            decoded = ""
            province = ""

            for name, _ in sorted_detections:
                if name in province_map:
                    province = label_dict.get(name, f"[{name}]")
                else:
                    decoded += label_dict.get(name, f"[{name}]")
            print("Decoded Text:", decoded)
            print("Province:", province)


            
            
            
            
            
            
            # for box in results[0].boxes:
            #     x1, y1, x2, y2 = box.xyxy[0]  # ตำแหน่งกรอบ
            #     conf = box.conf[0]            # ความมั่นใจ
            #     cls = box.cls[0]              # class id
            #     # print(f"Box: {x1}, {y1}, {x2}, {y2} | Confidence: {conf} | Class: {cls}")

            # หรือดูผลลัพธ์ทั้งหมด
            print("WH: ",results[0].boxes.xyxy)      # numpy array ของกรอบทั้งหมด
            print("confidence: ",results[0].boxes.conf)      # confidence ของแต่ละกรอบ
            print("class: ",results[0].boxes.cls)    
            

            # print(cv2.IMREAD_COLOR)
            # print(type(cv2.IMREAD_COLOR))
            # print(frame.shape)

            
            # # load image with PIL
            # image = Image.open(io.BytesIO(decoded))
            # print(type(image) )
            # สมมติว่ามีการประมวลผลต่อ
            # res = {"text": len(decoded), "confidence": 0.99}
            res = {"regNum": decoded, "Province": province}
            return res
        except Exception as e:
            print(f"Error in OCR prediction: {e}")
            return {"error": "OCR prediction failed"}
        
    
    
    def decode_base64(self, img_base64: str) -> str:
        try:
            
            # cut prefix (data:image/jpeg;base64,)
            if "," in img_base64:
                img_base64 = img_base64.split(",")[1]
                
            # decode base64 (raw bytes)
            imgData = base64.b64decode(img_base64)
            
            #   save to img 
            # with open("./app/img/output.jpg", "wb") as image_file:
            #     image_file.write(imgData)
            
            
            return imgData
        
        except Exception as e:
            print(f"Error decoding base64 image: {e}")
            return "Decode Base64 error"
        
    def preProcess(self):
        pass
    
    def regnizeText(self):
        


        pass