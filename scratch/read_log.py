import os
import shutil

log_path = r"C:\Users\Mohommed Adil\.gemini\antigravity\brain\3e6265db-7f61-4541-9259-62580c64c8f6\.system_generated\tasks\task-7781.log"
copy_path = r"c:\Users\Mohommed Adil\Desktop\Vision Query\scratch\log_copy.txt"

if os.path.exists(log_path):
    try:
        shutil.copy2(log_path, copy_path)
        with open(copy_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            print(f"Total lines: {len(lines)}")
            print("--- LAST 100 LINES ---")
            for idx, line in enumerate(lines[-100:]):
                safe_line = line.encode('ascii', errors='replace').decode('ascii').strip()
                print(f"{len(lines)-100+idx+1}: {safe_line}")
    except Exception as e:
        print("Error:", e)
else:
    print("Log file does not exist")
