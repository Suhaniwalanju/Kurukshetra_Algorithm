import os
import subprocess
import shutil

def convert_pptx_to_pdf(pptx_path: str, pdf_path: str) -> bool:
    os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
    abs_pptx = os.path.abspath(pptx_path)
    abs_pdf = os.path.abspath(pdf_path)

    # 1. Try LibreOffice if available
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        for cand in [r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"]:
            if os.path.exists(cand):
                soffice = cand
                break

    if soffice:
        out_dir = os.path.dirname(abs_pdf)
        cmd = [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, abs_pptx]
        res = subprocess.run(cmd, capture_output=True, timeout=60)
        base = os.path.splitext(os.path.basename(abs_pptx))[0]
        gen_pdf = os.path.join(out_dir, f"{base}.pdf")
        if os.path.exists(gen_pdf):
            if gen_pdf != abs_pdf:
                shutil.move(gen_pdf, abs_pdf)
            return True

    # 2. Try PowerPoint COM on Windows
    ps_cmd = (
        f"$p = New-Object -ComObject PowerPoint.Application; "
        f"$pres = $p.Presentations.Open('{abs_pptx}', 1, 0, 0); "
        f"$pres.SaveAs('{abs_pdf}', 32); "
        f"$pres.Close(); "
        f"$p.Quit();"
    )
    res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd], capture_output=True, text=True, timeout=60)
    if os.path.exists(abs_pdf):
        return True

    return False

if __name__ == "__main__":
    pptx = "output/test_notes_single_slide_deck/Python_Scripting_Python.pptx"
    pdf = "output/test_notes_single_slide_deck/test_output.pdf"
    ok = convert_pptx_to_pdf(pptx, pdf)
    print("SUCCESS:", ok, "PDF exists:", os.path.exists(pdf))
    if os.path.exists(pdf):
        print("Size:", os.path.getsize(pdf))
        os.remove(pdf)
