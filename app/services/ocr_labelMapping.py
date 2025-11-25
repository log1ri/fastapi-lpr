# 0-9
label_dict = {str(i): str(i) for i in range(10)}  
# print("0-9:", label_dict)
    
# A01-A44 → ก - ฮ
exclude_chars = ['ฤ', 'ฦ']
# for i in range(1, 45):
#     key = f"A{str(i).zfill(2)}"
#     label_dict[key] = chr(ord('ก') + i - 1)
exclude_chars = ['ฤ', 'ฦ']
i = 1
a_index = 1
while a_index <= 44:
    char = chr(ord('ก') + i - 1)
    
    if char in exclude_chars:
        i += 1
        continue
    key = f"A{str(a_index).zfill(2)}"
    label_dict[key] = char
    i += 1
    a_index += 1
# print("add A:", label_dict)
    
# province codes
province_map = {
    "KBI": "กระบี่", "KRI": "กาญจนบุรี", "KSN": "กาฬสินธุ์", "KPT": "กำแพงเพชร", "KKN": "ขอนแก่น",
    "CTI": "จันทบุรี", "CCO": "ฉะเชิงเทรา", "CBI": "ชลบุรี", "CNT": "ชัยนาท", "CPM": "ชัยภูมิ",
    "CPN": "ชุมพร", "CRI": "เชียงราย", "CMI": "เชียงใหม่", "TRG": "ตรัง", "TRT": "ตราด",
    "TAK": "ตาก", "NYK": "นครนายก", "NPT": "นครปฐม", "NPM": "นครพนม", "NMA": "นครราชสีมา",
    "NRT": "นครศรีธรรมราช", "NSN": "นครสวรรค์", "NBI": "นนทบุรี", "NWT": "นราธิวาส", "NAN": "น่าน",
    "BKN": "บึงกาฬ", "BRM": "บุรีรัมย์", "PTE": "ปทุมธานี", "PKN": "ประจวบคีรีขันธ์", "PRI": "ปราจีนบุรี",
    "PTN": "ปัตตานี", "PYO": "พะเยา", "AYA": "พระนครศรีอยุธยา", "PNA": "พังงา", "PLG": "พัทลุง",
    "PCT": "พิจิตร", "PLK": "พิษณุโลก", "PBI": "เพชรบุรี", "PNB": "เพชรบูรณ์", "PRE": "แพร่",
    "PKT": "ภูเก็ต", "MKM": "มหาสารคาม", "MDH": "มุกดาหาร", "MSN": "แม่ฮ่องสอน", "YST": "ยโสธร",
    "YLA": "ยะลา", "RET": "ร้อยเอ็ด", "RNG": "ระนอง", "RYG": "ระยอง", "RBR": "ราชบุรี",
    "LRI": "ลพบุรี", "LPG": "ลำปาง", "LPN": "ลำพูน", "LEI": "เลย", "SSK": "ศรีสะเกษ",
    "SNK": "สกลนคร", "SKA": "สงขลา", "STN": "สตูล", "SPK": "สมุทรปราการ", "SKM": "สมุทรสงคราม",
    "SKN": "สมุทรสาคร", "SKW": "สระแก้ว", "SRI": "สระบุรี", "SBR": "สิงห์บุรี", "STI": "สุโขทัย",
    "SPB": "สุพรรณบุรี", "SNI": "สุราษฎร์ธานี", "SRN": "สุรินทร์", "NKI": "หนองคาย", "NBP": "หนองบัวลำภู",
    "ATG": "อ่างทอง", "ACR": "อำนาจเจริญ", "UDN": "อุดรธานี", "UTT": "อุตรดิตถ์", "UTI": "อุทัยธานี",
    "UBN": "อุบลราชธานี", "BKK": "กรุงเทพมหานคร"
}

label_dict.update(province_map)

# print("Final label_dict:", label_dict)