import pyautogui
import pytesseract
import keyboard
import requests
from PIL import ImageGrab
import tkinter as tk
from tkinter import messagebox, scrolledtext
import winsound
import time
import threading
import cv2
import numpy as np
import os
import subprocess
import json
import sys # --- NEW: Required for platform checks ---

# --- Configuration ---
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OLLAMA_API_URL = "http://localhost:11434"
MODEL_NAME = "phi3:latest"

class OCRAssistant:
    """
    An AI-powered assistant that performs OCR on a selected screen region
    and processes the text using a local Ollama model.
    """
    def __init__(self):
        self.selected_region = None
        self.running = False
        self._processing_lock = threading.Lock()
        self.ollama_process = None # --- NEW: To hold the background Ollama process ---
        
        self.tasks = {
            "Answer Question": "Answer the question based on the text.",
            "Summarize Text": "Provide a concise summary of the text.",
            "Explain Simply": "Explain the text in simple terms.",
            "Translate to English": "Translate the text into English."
        }
        self.prompts = {
            "Answer Question": "You are an expert Q&A assistant. Based *only* on the text below, answer the user's implicit question concisely. If the text is not a question, treat it as a request for explanation.\n\nText: \"{text}\"",
            "Summarize Text": "You are an expert summarizer. Provide a clear and concise summary of the following text.\n\nText: \"{text}\"",
            "Explain Simply": "You are an expert educator. Explain the core concept of the following text in simple, easy-to-understand terms.\n\nText: \"{text}\"",
            "Translate to English": "You are an expert translator. Translate the following text accurately into English.\n\nText: \"{text}\"",
        }

        self.setup_gui()

    # --- 1. Dependency and Setup Methods ---

    def setup_gui(self):
        """Creates the main application window and its widgets."""
        self.root = tk.Tk()
        self.root.title("OCR AI Assistant")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        self.center_window(self.root, 400, 300)
        self.root.attributes("-topmost", True)

        BG_COLOR = "#f0f0f0"
        BTN_COLOR_START = "#27ae60"
        BTN_COLOR_STOP = "#e74c3c"
        FONT_BOLD = ("Arial", 12, "bold")
        FONT_NORMAL = ("Arial", 10)
        
        self.root.config(bg=BG_COLOR)

        title = tk.Label(self.root, text="OCR AI Assistant", font=("Arial", 16, "bold"), bg=BG_COLOR)
        title.pack(pady=(15, 5))

        instructions = tk.Label(self.root, 
            text="Alt+R: Select Region\nAlt+T: Capture & Process",
            font=FONT_NORMAL, justify="center", bg=BG_COLOR)
        instructions.pack(pady=5)

        task_frame = tk.Frame(self.root, bg=BG_COLOR)
        task_frame.pack(pady=10, fill="x", padx=20)
        
        tk.Label(task_frame, text="AI Task:", font=FONT_BOLD, bg=BG_COLOR).pack(side="left", padx=(0, 10))
        self.selected_task = tk.StringVar(self.root)
        self.selected_task.set(list(self.tasks.keys())[0])
        
        task_menu = tk.OptionMenu(task_frame, self.selected_task, *self.tasks.keys())
        task_menu.config(font=FONT_NORMAL, width=18)
        task_menu.pack(side="left", expand=True, fill="x")

        button_frame = tk.Frame(self.root, bg=BG_COLOR)
        button_frame.pack(pady=15)
        
        self.start_btn = tk.Button(button_frame, text="Start", command=self.start,
                                   width=12, bg=BTN_COLOR_START, fg="white", font=FONT_BOLD, relief="flat")
        self.start_btn.pack(side="left", padx=10)
        
        self.stop_btn = tk.Button(button_frame, text="Stop", command=self.stop,
                                  width=12, bg=BTN_COLOR_STOP, fg="white", font=FONT_BOLD, relief="flat", state="disabled")
        self.stop_btn.pack(side="left", padx=10)

        self.status_var = tk.StringVar(self.root, "Checking dependencies...")
        status_bar = tk.Label(self.root, textvariable=self.status_var, font=("Arial", 9), fg="gray", bg=BG_COLOR)
        status_bar.pack(side="bottom", fill="x", pady=5, padx=10)

        self.root.after(200, self.startup_check)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close) # --- MODIFIED: Ensure clean shutdown ---

    def startup_check(self):
        """Validates dependencies in a background thread to keep the GUI responsive."""
        self.status_var.set("Validating dependencies...")
        threading.Thread(target=self._validate_dependencies_thread, daemon=True).start()

    # --- MODIFIED: Updated dependency check logic ---
    def _validate_dependencies_thread(self):
        """The actual validation logic, now with auto-start capability."""
        issues = []
        if not self._check_tesseract():
            issues.append(f"Tesseract not found at: {TESSERACT_PATH}")
        
        # Check if Ollama service is running
        if not self._check_ollama_service():
            self.root.after(0, lambda: self.status_var.set("Ollama not found, attempting to start..."))
            # If not running, try to start it and check again
            if not self._start_ollama_service() or not self._check_ollama_service():
                issues.append("Ollama service failed to start. Run 'ollama serve' manually.")
            else:
                self.root.after(0, lambda: self.status_var.set("Ollama started successfully."))
        
        # If we have no issues so far, check for the model
        if not issues and not self._check_model_availability():
            issues.append(f"{MODEL_NAME} not found (try 'ollama pull {MODEL_NAME}')")

        def update_gui():
            if not issues:
                self.status_var.set("Ready to start.")
                self.start_btn.config(state="normal")
            else:
                error_msg = "Issues found:\n\n" + "\n".join(f"• {issue}" for issue in issues)
                self.status_var.set("Dependency error!")
                messagebox.showerror("Dependencies Required", error_msg)
        
        self.root.after(0, update_gui)

    # --- Function to start Ollama in the background ---
    def _start_ollama_service(self):
        """Tries to start the Ollama service silently in the background."""
        try:
            subprocess.run(["ollama", "--version"], check=True, capture_output=True, text=True)
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW
            self.ollama_process = subprocess.Popen(["ollama", "serve"], creationflags=creationflags)
            time.sleep(5)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
        except Exception as e:
            print(f"Error starting Ollama service: {e}")
            return False

    def _check_tesseract(self):
        """Checks if Tesseract is correctly configured."""
        if os.path.exists(TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
            return True
        return False

    def _check_ollama_service(self):
        """Checks if the Ollama service is running."""
        try:
            return requests.get(OLLAMA_API_URL, timeout=3).status_code == 200
        except requests.exceptions.RequestException:
            return False

    def _check_model_availability(self):
        """Checks if the required model is available in Ollama."""
        try:
            response = requests.get(f"{OLLAMA_API_URL}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return any(MODEL_NAME in model.get("name", "") for model in models)
            return False
        except requests.exceptions.RequestException:
            return False

    # --- 2. Core Functionality ---
    
    def start(self):
        """Starts the hotkey listeners."""
        if self.running: return
        self.running = True

        keyboard.add_hotkey("alt+r", lambda: self.root.after(0, self.select_region))
        keyboard.add_hotkey("alt+t", lambda: self.root.after(0, self.run_capture_thread))
        
        self.status_var.set("Running | Use hotkeys.")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def stop(self):
        """Stops the hotkey listeners."""
        if not self.running: return
        self.running = False
        
        keyboard.unhook_all_hotkeys()
        
        self.status_var.set("Stopped.")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def select_region(self):
        """Allows the user to select a screen region using a transparent overlay."""
        self.root.withdraw()
        
        overlay = tk.Toplevel(self.root)
        overlay.attributes("-fullscreen", True, "-alpha", 0.3, "-topmost", True)
        overlay.configure(bg='black')
        
        canvas = tk.Canvas(overlay, cursor="cross", bg='black', highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        start_pos = {}
        rect = None

        def on_click(event):
            start_pos['x'], start_pos['y'] = event.x, event.y
            nonlocal rect
            rect = canvas.create_rectangle(0, 0, 0, 0, outline="red", width=2)
        
        def on_drag(event):
            canvas.coords(rect, start_pos['x'], start_pos['y'], event.x, event.y)
        
        def on_release(event):
            x1, y1 = start_pos['x'], start_pos['y']
            x2, y2 = event.x, event.y
            self.selected_region = (min(x1, x2), min(y1, y2), abs(x2-x1), abs(y2-y1))
            self.status_var.set(f"Region set: {self.selected_region[2]}x{self.selected_region[3]}")
            overlay.destroy()
            self.root.deiconify()

        def on_cancel(event):
            self.status_var.set("Selection cancelled.")
            overlay.destroy()
            self.root.deiconify()

        canvas.bind("<Button-1>", on_click)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.bind("<Escape>", on_cancel)
        overlay.focus_set()

    def run_capture_thread(self):
        """Initiates the capture and processing in a new thread to keep GUI alive."""
        if not self.selected_region:
            messagebox.showwarning("No Region", "Please select a region with Alt+R first.")
            return

        if not self._processing_lock.acquire(blocking=False):
            self.status_var.set("Already processing...")
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return

        threading.Thread(target=self._capture_and_process, daemon=True).start()

    def _capture_and_process(self):
        """The core workflow: captures screen, performs OCR, and streams AI response."""
        try:
            self.root.after(0, lambda: self.status_var.set("Capturing & OCR..."))
            x, y, w, h = self.selected_region
            screenshot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            
            img_np = np.array(screenshot)
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            gray = cv2.medianBlur(gray, 1)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            custom_config = r'--oem 3 --psm 6'
            text = pytesseract.image_to_string(binary, config=custom_config).strip()

            if not text:
                self.root.after(0, lambda: self.status_var.set("No text found."))
                self.root.after(0, lambda: messagebox.showinfo("No Text", "Could not detect any text in the selected region."))
                return

            self.root.after(0, lambda: self.status_var.set("Asking AI..."))
            result_window, text_widget = self.create_result_window()
            self._stream_ai_response(text, text_widget)

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"An unexpected error occurred: {e}"))
            self.root.after(0, lambda: self.status_var.set("Error!"))
        finally:
            self._processing_lock.release()

    def _stream_ai_response(self, text, text_widget):
        """Streams the response from Ollama and updates the result window live."""
        task = self.selected_task.get()
        # VERY IMPORTANT: Prompt is set for concise, direct answers only.
        prompt = (
            "You are an expert assistant. Read the following text and provide a direct, concise, factual answer in one line. "
            "Do not repeat the question, do not list options, do not use letters or bullet points. "
            "Just answer in one clear sentence.\n\n"
            f"Text: \"{text}\"\n\n"
            "Answer:"
        )
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": 0.3, "top_p": 0.9}
        }
        try:
            response = requests.post(f"{OLLAMA_API_URL}/api/generate", json=payload, stream=True, timeout=30)
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    content = chunk.get("response", "")
                    self.root.after(0, self.update_text_widget, text_widget, content)
                    if chunk.get("done"):
                        self.root.after(0, lambda: self.status_var.set("Done."))
                        break
        except requests.exceptions.Timeout:
            error_msg = "AI response timed out."
            self.root.after(0, self.update_text_widget, text_widget, f"\n\n--- ERROR ---\n{error_msg}")
            self.root.after(0, lambda: self.status_var.set("Timeout!"))
        except requests.exceptions.RequestException as e:
            error_msg = f"API Error: {e}"
            self.root.after(0, self.update_text_widget, text_widget, f"\n\n--- ERROR ---\n{error_msg}")
            self.root.after(0, lambda: self.status_var.set("API Error!"))
        finally:
            self.root.after(0, lambda: text_widget.config(state="disabled"))
    
    # --- 3. GUI Helpers and Main Loop ---

    def create_result_window(self):
        """Creates the pop-up window to display the streaming AI response."""
        result_window = tk.Toplevel(self.root)
        result_window.title(f"AI Response: {self.selected_task.get()}")
        result_window.geometry("600x400")
        self.center_window(result_window, 600, 400)
        result_window.attributes("-topmost", True)

        text_widget = scrolledtext.ScrolledText(result_window, wrap="word", font=("Consolas", 11),
                                                padx=10, pady=10, relief="flat")
        text_widget.pack(fill="both", expand=True)
        text_widget.insert("1.0", "AI is thinking...")
        
        def copy_text():
            result_window.clipboard_clear()
            result_window.clipboard_append(text_widget.get("1.0", "end-1c"))
        
        button_frame = tk.Frame(result_window)
        button_frame.pack(pady=5)
        tk.Button(button_frame, text="Copy All", command=copy_text).pack(side="left", padx=5)
        tk.Button(button_frame, text="Close", command=result_window.destroy).pack(side="left", padx=5)
        
        winsound.MessageBeep(winsound.MB_OK)
        result_window.focus_set()
        
        text_widget.after(100, lambda: text_widget.delete("1.0", "end"))

        return result_window, text_widget
    
    def update_text_widget(self, text_widget, content):
        """Appends content to the text widget, ensuring it's scrolled to the end."""
        text_widget.config(state="normal")
        text_widget.insert("end", content)
        text_widget.see("end")
        text_widget.config(state="disabled")

    def center_window(self, window, width, height):
        """Centers a tkinter window on the screen."""
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = (screen_w // 2) - (width // 2)
        y = (screen_h // 2) - (height // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    # --- Handles clean shutdown of the app AND the background process ---
    def on_close(self):
        """Handles the clean shutdown of the application."""
        self.stop()
        # Terminate the background Ollama process if we started it
        if self.ollama_process:
            self.ollama_process.terminate()
            print("Ollama background process terminated.")
        self.root.destroy()

    def run(self):
        """Starts the tkinter main loop."""
        self.root.mainloop()

# --- Main Entry Point ---
if __name__ == "__main__":
    app = OCRAssistant()
    app.run()