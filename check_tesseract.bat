@echo off
where tesseract
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
tesseract --version
pause
