# Alex’s Receipt Parser

**A smarter (I think?) way to split receipts.**
This is a personal project that I made since I got annoyed at manually typing out receipts, especially since I went to Costco with 4 friends and had to split like $1000+ and it took me 30 minutes and a spreadsheet to do so. I hope you enjoy! Please do let me know if there are bugs!

---

## Very High Level Design Diagram
(I used Excalidraw if curious)
<img width="989" height="594" alt="Screenshot 2025-11-13 at 5 08 20 pm" src="https://github.com/user-attachments/assets/18e69460-02e7-4ca5-8639-2ba3d8426d24" />

---

## Tech Stack

### **Frontend**
- **React + Vite** — fast development with hot-reload.  
- **Netlify** — hosting and CI/CD deployment.  
- **Axios** — API communication with backend.

### **Backend**
- **Modal** — serverless Python backend.  
- **FastAPI** — image upload and inference routing.  
- **HuggingFace Donut** — OCR + structured text extraction.  
- **OpenCV + Pillow** — image preprocessing (contrast, grayscale, denoising).

---

## How It Works

1. **Upload a photo** of your receipt.  
2. **Backend preprocessing** enhances image contrast and readability.  
3. **The Donut model** extracts items as structured JSON.  
4. **Frontend UI** displays an editable table where you can:
   - Edit item names, prices, or quantities.
   - Assign people to each item.
   - View per-person and total costs.

---

## Live Demo
If you wanna try it out for yourself:

**[alexs-receipt-parser.netlify.app](https://alexs-receipt-parser.netlify.app/)**

---

## Local Setup
If you wanna run it for yourself:

```bash
# Clone the repo
git clone https://github.com/yangalex1081/receipt_parser.git

# Frontend setup
cd receipt-parser-frontend
npm install
npm run dev

# Backend setup
cd receipt-parser-api
modal deploy api.py

```

## Security
- All backend calls require an API key stored in `.env` (`VITE_API_KEY`)
- Modal secrets are used for the same API key for authorisation
- No sensitive data is logged or stored at all

## Contact
Built by Alex Yang
[LinkedIn](https://www.linkedin.com/in/waynealexanderyang/)
Email: yangalex1081@gmail.com
