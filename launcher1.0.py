import os
import json
import urllib.request
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

# =====================================================================
# 1. UNVERÄNDERTER GENERATOR-CODE
# =====================================================================
executor = ThreadPoolExecutor(max_workers=32)

def fast_download(url, path):
    if os.path.exists(path): return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with open(path, 'wb') as out_file: out_file.write(response.read())
        return
    except Exception: pass
    if "resources.download.minecraft.net" in url or "libraries.minecraft.net" in url:
        fallback = url.replace("https://resources.download.minecraft.net", "https://bmclapi2.bangbang93.com/assets")
        fallback = fallback.replace("https://libraries.minecraft.net", "https://bmclapi2.bangbang93.com/maven")
        try: urllib.request.urlretrieve(fallback, path)
        except Exception as e: print(f"Download-Fehler: {e}")

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response: return json.loads(response.read().decode())

class MCFullInstanceGenerator:
    def __init__(self, root):
        self.root = root
        self.root.title("MC Instance Generator - Fabric Fixed")
        self.root.geometry("650x500")
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.instances_dir = os.path.join(self.base_path, "instances")
        self.name_var = tk.StringVar()
        self.version_var = tk.StringVar(value="Lade...")
        self.loader_var = tk.StringVar(value="Vanilla")
        self.status_var = tk.StringVar(value="Status: Bereit")
        self.setup_environment()
        self.create_widgets()
        threading.Thread(target=self.load_versions, daemon=True).start()

    def setup_environment(self): os.makedirs(self.instances_dir, exist_ok=True)

    def create_widgets(self):
        frame = ttk.Frame(self.root, padding=20); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Minecraft Instance Generator", font=("Arial", 14, "bold")).pack(pady=10)
        ttk.Label(frame, text="Instanzname:").pack(anchor="w")
        ttk.Entry(frame, textvariable=self.name_var).pack(fill="x", pady=5)
        ttk.Label(frame, text="Minecraft Version:").pack(anchor="w")
        self.combo = ttk.Combobox(frame, textvariable=self.version_var, state="readonly"); self.combo.pack(fill="x", pady=5)
        ttk.Label(frame, text="Mod-Loader:").pack(anchor="w")
        self.loader_combo = ttk.Combobox(frame, textvariable=self.loader_var, values=["Vanilla", "Fabric"], state="readonly"); self.loader_combo.pack(fill="x", pady=5)
        ttk.Button(frame, text="Instanz generieren", command=self.start_generation).pack(fill="x", pady=15)
        ttk.Label(frame, textvariable=self.status_var).pack(anchor="w", pady=5)
        self.progress = ttk.Progressbar(frame, orient="horizontal", length=500, mode="determinate"); self.progress.pack(pady=10, fill="x")

    def update_progress(self, value, maximum):
        self.progress["value"] = value; self.progress["maximum"] = maximum; self.root.update_idletasks()

    def load_versions(self):
        try:
            manifest = get_json("https://launchermeta.mojang.com/mc/game/version_manifest_v2.json")
            releases = [v["id"] for v in manifest["versions"] if v["type"] == "release"]
            self.manifest = manifest; self.combo["values"] = releases
            if releases: self.version_var.set(releases[0])
        except Exception: self.status_var.set("Fehler beim Laden der Mojang-API")

    def start_generation(self): threading.Thread(target=self.generate_instance, daemon=True).start()

    def generate_instance(self):
        name = self.name_var.get().strip(); base_version = self.version_var.get(); loader = self.loader_var.get()
        if not name: messagebox.showwarning("Eingabe fehlt", "Bitte einen Namen für die Instanz wählen."); return
        inst_path = os.path.join(self.instances_dir, name)
        mcroot = os.path.join(inst_path, ".minecraft")
        versions_dir = os.path.join(mcroot, "versions")
        if os.path.exists(inst_path): messagebox.showerror("Fehler", "Dieser Instanz-Ordner existiert bereits."); return
        try:
            self.status_var.set(f"Lade Vanilla {base_version} Metadaten...")
            entry = next(v for v in self.manifest["versions"] if v["id"] == base_version)
            vanilla_json_data = get_json(entry["url"])
            vanilla_ver_dir = os.path.join(versions_dir, base_version); os.makedirs(vanilla_ver_dir, exist_ok=True)
            with open(os.path.join(vanilla_ver_dir, f"{base_version}.json"), "w") as f: json.dump(vanilla_json_data, f, indent=4)
            self.status_var.set("Lade Vanilla JAR...")
            fast_download(vanilla_json_data["downloads"]["client"]["url"], os.path.join(vanilla_ver_dir, f"{base_version}.jar"))
            
            fabric_json_data = None
            if loader == "Fabric":
                self.status_var.set("Lade Fabric Metadaten...")
                loader_list = get_json("https://meta.fabricmc.net/v2/versions/loader")
                latest_loader = loader_list[0]["version"]
                fabric_id = f"fabric-loader-{latest_loader}-{base_version}"
                fabric_ver_dir = os.path.join(versions_dir, fabric_id); os.makedirs(fabric_ver_dir, exist_ok=True)
                profile_url = f"https://meta.fabricmc.net/v2/versions/loader/{base_version}/{latest_loader}/profile/json"
                fabric_json_data = get_json(profile_url)
                with open(os.path.join(fabric_ver_dir, f"{fabric_id}.json"), "w") as f: json.dump(fabric_json_data, f, indent=4)
                self.status_var.set("Fabric Profil erstellt.")

            all_libs = vanilla_json_data.get("libraries", []).copy()
            if fabric_json_data: all_libs.extend(fabric_json_data.get("libraries", []))
            self.status_var.set(f"Lade {len(all_libs)} Libraries...")
            lib_tasks = []; seen_paths = set()
            for lib in all_libs:
                if "downloads" in lib and "artifact" in lib["downloads"]:
                    art = lib["downloads"]["artifact"]; p = os.path.join(mcroot, "libraries", art["path"])
                    if p not in seen_paths: lib_tasks.append(executor.submit(fast_download, art["url"], p)); seen_paths.add(p)
                elif "url" in lib:
                    parts = lib["name"].split(":"); rel = f"{parts[0].replace('.','/')}/{parts[1]}/{parts[2]}/{parts[1]}-{parts[2]}.jar"
                    p = os.path.join(mcroot, "libraries", rel)
                    if p not in seen_paths: lib_tasks.append(executor.submit(fast_download, lib["url"] + rel, p)); seen_paths.add(p)
            for i, t in enumerate(lib_tasks): t.result(); self.update_progress(i + 1, len(lib_tasks))

            self.status_var.set("Lade Assets (Sounds, Texturen)...")
            asset_index_url = vanilla_json_data["assetIndex"]["url"]; asset_id = vanilla_json_data["assets"]
            fast_download(asset_index_url, os.path.join(mcroot, "assets", "indexes", f"{asset_id}.json"))
            asset_data = get_json(asset_index_url); objs = asset_data.get("objects", {})
            asset_tasks = []
            for v in objs.values():
                h = v['hash']; url = f"https://resources.download.minecraft.net/{h[:2]}/{h}"; path = os.path.join(mcroot, "assets", "objects", h[:2], h)
                asset_tasks.append(executor.submit(fast_download, url, path))
            for i, t in enumerate(asset_tasks):
                t.result()
                if i % 100 == 0: self.update_progress(i + 1, len(asset_tasks))
            self.status_var.set("Fertig!")
            messagebox.showinfo("Erfolg", f"Instanz '{name}' wurde erfolgreich generiert!")
        except Exception as e:
            self.status_var.set("Fehler!"); messagebox.showerror("Fehler beim Erstellen", str(e))

# =====================================================================
# 2. LAUNCHER-CODE 
# =====================================================================
try:
    import requests
    from PIL import Image, ImageTk, ImageDraw
except Exception as e:
    messagebox.showerror("Fehlendes Modul", f"Ein benötigtes Modul fehlt:\n\n{e}\n\nBitte installiere:\npython -m pip install requests pillow")
    raise

minecraft_process = None
logging_enabled = False
icon_cache = {}
versions_cache = {}
page_cache = {}

def get_mc_dir():
    inst = instance_var.get()
    if not inst: return os.path.join(os.getcwd(), ".minecraft")
    return os.path.join(os.getcwd(), "instances", inst, ".minecraft")

def get_current_mc_version(mc_dir):
    v_dir = os.path.join(mc_dir, "versions")
    if os.path.exists(v_dir):
        for d in os.listdir(v_dir):
            if not d.startswith("fabric"):
                if os.path.exists(os.path.join(v_dir, d, f"{d}.jar")): return d
    return "1.21.1" 

def create_placeholder_icon(text, color):
    img = Image.new('RGB', (40, 40), color=color)
    d = ImageDraw.Draw(img)
    d.text((10, 10), text, fill=(255, 255, 255))
    return ImageTk.PhotoImage(img)

def log(text):
    if not logging_enabled: return
    log_box.config(state="normal")
    if "ERROR" in text or "Exception" in text or "❌" in text: tag = "red"
    elif "WARN" in text: tag = "yellow"
    else: tag = "lime"
    log_box.insert(tk.END, text + "\n", tag)
    log_box.see(tk.END)
    log_box.config(state="disabled")

def show_content_list():
    log_box.pack_forget()
    content_canvas_frame.pack(fill="both", expand=True, pady=10)
    for widget in content_list_frame.winfo_children(): widget.destroy()

    mc = get_mc_dir()
    # HIER FIX: Datapacks auf den korrekten Ordner "datapacks" gesetzt
    sections = {
        "🧩 Mods": ("mods", "#4a90e2", "JAR"),
        "📦 Datapacks": ("datapacks", "#e67e22", "ZIP"), 
        "✨ Shaderpacks": ("shaderpacks", "#9b59b6", "ZIP"),
        "🎨 Resourcepacks": ("resourcepacks", "#2ecc71", "ZIP")
    }

    tk.Label(content_list_frame, text=f"Instanz: {instance_var.get() or 'Keine'}", font=("Segoe UI", 16, "bold"), bg="#1e1e1e", fg="#00aaff").pack(anchor="w", pady=10, padx=10)

    for title, info in sections.items():
        folder_name, color, ext = info
        path = os.path.join(mc, folder_name)
        tk.Label(content_list_frame, text=title, font=("Segoe UI", 14, "bold"), bg="#1e1e1e", fg="white").pack(anchor="w", padx=10, pady=(10, 0))
        tk.Frame(content_list_frame, bg="#555", height=1).pack(fill="x", padx=10, pady=5)

        if not os.path.exists(path):
            tk.Label(content_list_frame, text="  (Ordner nicht gefunden)", bg="#1e1e1e", fg="#888").pack(anchor="w", padx=20)
            continue

        items = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        if not items:
            tk.Label(content_list_frame, text="  (leer)", bg="#1e1e1e", fg="#888").pack(anchor="w", padx=20)
            continue

        for item in items:
            item_frame = tk.Frame(content_list_frame, bg="#2a2a2a")
            item_frame.pack(fill="x", padx=20, pady=2)
            icon = create_placeholder_icon(ext, color)
            lbl_icon = tk.Label(item_frame, image=icon, bg="#2a2a2a")
            lbl_icon.image = icon
            lbl_icon.pack(side="left", padx=5, pady=5)
            tk.Label(item_frame, text=item, bg="#2a2a2a", fg="white", font=("Segoe UI", 11)).pack(side="left", padx=10)

def start_minecraft():
    global minecraft_process
    set_stop_button()
    mc_dir = get_mc_dir()
    mc_version = get_current_mc_version(mc_dir)

    loader = None
    if os.path.exists(os.path.join(mc_dir, "libraries")):
        for root_dir, dirs, files in os.walk(os.path.join(mc_dir, "libraries")):
            for f in files:
                if f.startswith("fabric-loader-") and f.endswith(".jar"):
                    loader = os.path.join(root_dir, f)
                    break
            if loader: break

    mcjar = os.path.join(mc_dir, "versions", mc_version, f"{mc_version}.jar")
    if not os.path.exists(mcjar):
        log(f"❌ Minecraft JAR nicht gefunden: {mcjar}")
        set_start_button(); return

    libs = []
    for root_dir, dirs, files in os.walk(os.path.join(mc_dir, "libraries")):
        for f in files:
            if f.endswith(".jar"): libs.append(os.path.join(root_dir, f))

    if loader:
        log("🚀 Starte Minecraft mit Fabric...")
        cp = ";".join([loader, mcjar] + libs)
        main_class = "net.fabricmc.loader.impl.launch.knot.KnotClient"
    else:
        log("🚀 Starte Vanilla Minecraft...")
        cp = ";".join([mcjar] + libs)
        main_class = "net.minecraft.client.main.Main"

    # HIER FIX: accessToken, uuid, username und userType hinzugefügt für Vanilla Start
    cmd = [
        "java", "-Xmx4G", "-Xms2G", "-cp", cp, main_class,
        "--gameDir", mc_dir,
        "--version", mc_version,
        "--assetsDir", os.path.join(mc_dir, "assets"),
        "--assetIndex", mc_version,
        "--username", "Player",
        "--accessToken", "0",
        "--uuid", "0",
        "--userType", "legacy"
    ]

    try:
        minecraft_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in minecraft_process.stdout: log(line.rstrip())
    except Exception as e: log(f"❌ Fehler beim Starten: {e}")
    set_start_button()

def start_thread(): threading.Thread(target=start_minecraft, daemon=True).start()
def stop_minecraft():
    global minecraft_process
    if minecraft_process and minecraft_process.poll() is None:
        minecraft_process.terminate(); log("⛔ Minecraft gestoppt")
    set_start_button()

def set_start_button(): start_button.config(text="Start", bg="#4CAF50", command=start_thread)
def set_stop_button(): start_button.config(text="Stop", bg="#d9534f", command=stop_minecraft)
def open_folder(): 
    d = get_mc_dir(); os.makedirs(d, exist_ok=True); os.startfile(d)

def toggle_logs():
    global logging_enabled
    logging_enabled = log_var.get()
    if logging_enabled:
        content_canvas_frame.pack_forget()
        log_box.pack(pady=10, fill="both", expand=True)
        log_box.config(state="normal"); log_box.delete("1.0", tk.END); log_box.config(state="disabled")
        log("✔ Logs aktiviert")
    else: show_content_list()

def load_icon_async(project_id, icon_url, label):
    if project_id in icon_cache:
        img_tk = icon_cache[project_id]; label.config(image=img_tk); label.image = img_tk
        return
    def worker():
        img_tk_local = None
        if icon_url:
            try:
                img_data = requests.get(icon_url, timeout=10).content
                img = Image.open(BytesIO(img_data)).resize((50, 50))
                img_tk_local = ImageTk.PhotoImage(img)
            except: pass
        def apply():
            if img_tk_local: icon_cache[project_id] = img_tk_local; label.config(image=img_tk_local); label.image = img_tk_local
        root.after(0, apply)
    threading.Thread(target=worker, daemon=True).start()

def open_modrinth_window():
    mod_window = tk.Toplevel(root); mod_window.title("Add Content – Modrinth"); mod_window.state("zoomed"); mod_window.configure(bg="#121212")
    mc_dir = get_mc_dir(); current_version = get_current_mc_version(mc_dir)
    state = {"category": "mod", "query": "", "page": 0, "pages": 1, "limit": 20}
    CATEGORY_MAP = {"Mods": "mod", "Shader": "shader", "Resourcepacks": "resourcepack", "Datapacks": "datapack"}
    FOLDER_MAP = {"mod": "mods", "shader": "shaderpacks", "resourcepack": "resourcepacks", "datapack": "datapacks"}

    cat_frame = tk.Frame(mod_window, bg="#121212"); cat_frame.pack(pady=10)
    def set_category(cat_key):
        state["category"] = CATEGORY_MAP[cat_key]; state["page"] = 0; search_var.set("")
        load_modrinth_page(state, scroll_frame, pagination_frame, current_version, mc_dir, FOLDER_MAP)

    for label in CATEGORY_MAP.keys():
        tk.Button(cat_frame, text=label, font=("Segoe UI", 14), bg="#333333", fg="white", bd=0, padx=15, pady=5, command=lambda l=label: set_category(l)).pack(side="left", padx=5)

    search_var = tk.StringVar()
    tk.Entry(mod_window, textvariable=search_var, font=("Segoe UI", 16), width=40).pack(pady=10)
    tk.Button(mod_window, text="Suchen", font=("Segoe UI", 16), bg="#3a8dde", fg="white", command=lambda: [state.update({"query": search_var.get(), "page": 0}), load_modrinth_page(state, scroll_frame, pagination_frame, current_version, mc_dir, FOLDER_MAP)]).pack()

    result_frame = tk.Frame(mod_window, bg="#121212"); result_frame.pack(fill="both", expand=True, pady=10)
    canvas = tk.Canvas(result_frame, bg="#121212", highlightthickness=0)
    scrollbar = tk.Scrollbar(result_frame, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas, bg="#121212")
    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw"); canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
    pagination_frame = tk.Frame(mod_window, bg="#121212"); pagination_frame.pack(pady=10)
    load_modrinth_page(state, scroll_frame, pagination_frame, current_version, mc_dir, FOLDER_MAP)

def load_modrinth_page(state, parent_frame, pagination_frame, current_version, mc_dir, folder_map):
    for widget in parent_frame.winfo_children(): widget.destroy()
    category = state["category"]; query = state["query"]; page = state["page"]; limit = state["limit"]; offset = page * limit
    key = (category, query.strip(), page)

    def build_ui_from_data(data):
        hits = data.get("hits", [])
        state["pages"] = max(1, (data.get("total_hits", len(hits)) + limit - 1) // limit)
        for hit in hits:
            mod_id = hit["project_id"]; name = hit["title"]; desc = hit["description"]; icon_url = hit.get("icon_url")
            frame = tk.Frame(parent_frame, bg="#1e1e1e", pady=10); frame.pack(fill="x", padx=20, pady=5)
            icon_label = tk.Label(frame, bg="#1e1e1e", width=50, height=50); icon_label.pack(side="left", padx=10)
            load_icon_async(mod_id, icon_url, icon_label)
            text_frame = tk.Frame(frame, bg="#1e1e1e"); text_frame.pack(side="left", fill="x", expand=True)
            tk.Label(text_frame, text=name, font=("Segoe UI", 14, "bold"), fg="white", bg="#1e1e1e").pack(anchor="w")
            tk.Label(text_frame, text=desc[:100]+"..." if len(desc)>100 else desc, font=("Segoe UI", 10), fg="#ccc", bg="#1e1e1e").pack(anchor="w")
            def install_mod(m_id=mod_id, m_name=name):
                try:
                    versions = versions_cache.get(m_id) or requests.get(f"https://api.modrinth.com/v2/project/{m_id}/version", timeout=10).json()
                    versions_cache[m_id] = versions
                    file = next((v["files"][0] for v in versions if current_version in v.get("game_versions", []) and v.get("files")), None)
                    if not file: messagebox.showerror("Fehler", f"Keine Version für {current_version} gefunden."); return
                    target_folder = folder_map.get(state["category"], "mods")
                    target_path = os.path.join(mc_dir, target_folder); os.makedirs(target_path, exist_ok=True)
                    file_data = requests.get(file["url"], timeout=20).content
                    with open(os.path.join(target_path, file["filename"]), "wb") as f: f.write(file_data)
                    messagebox.showinfo("Installiert", f"{m_name} installiert!"); show_content_list()
                except Exception as e: messagebox.showerror("Fehler", f"Installation fehlgeschlagen:\n{e}")
            tk.Button(frame, text="Installieren", bg="#4CAF50", fg="white", command=install_mod).pack(side="right", padx=20)

        for w in pagination_frame.winfo_children(): w.destroy()
        def go_page(p):
            if 0 <= p < state["pages"]: state["page"] = p; load_modrinth_page(state, parent_frame, pagination_frame, current_version, mc_dir, folder_map)
        tk.Button(pagination_frame, text="«", bg="#333", fg="white", command=lambda: go_page(state["page"] - 1)).pack(side="left", padx=5)
        for p in range(max(0, min(state["page"] - 4, state["pages"] - 10)), min(state["pages"], max(0, min(state["page"] - 4, state["pages"] - 10)) + 10)):
            tk.Button(pagination_frame, text=str(p + 1), bg="#3a8dde" if p == state["page"] else "#333", fg="white", command=lambda pp=p: go_page(pp)).pack(side="left", padx=2)
        tk.Button(pagination_frame, text="»", bg="#333", fg="white", command=lambda: go_page(state["page"] + 1)).pack(side="left", padx=5)

    if key in page_cache: build_ui_from_data(page_cache[key]); return
    def worker():
        try:
            url = f"https://api.modrinth.com/v2/search?query={query}&facets=[[\"project_type:{category}\"]]&versions=[\"{current_version}\"]&limit={limit}&offset={offset}"
            data = requests.get(url, timeout=10).json(); page_cache[key] = data; root.after(0, lambda: build_ui_from_data(data))
        except Exception as e: root.after(0, lambda: messagebox.showerror("Fehler", str(e)))
    threading.Thread(target=worker, daemon=True).start()

# =====================================================================
# UI
# =====================================================================
root = tk.Tk(); root.title("Fabric Launcher & Generator"); root.state("zoomed"); root.configure(bg="#121212")
top_frame = tk.Frame(root, bg="#121212"); top_frame.pack(pady=10)
tk.Label(top_frame, text="Instanz:", bg="#121212", fg="white", font=("Segoe UI", 16)).pack(side="left", padx=5)
instance_var = tk.StringVar(); instance_combo = ttk.Combobox(top_frame, textvariable=instance_var, state="readonly", font=("Segoe UI", 14), width=25); instance_combo.pack(side="left", padx=5)

def refresh_instances():
    os.makedirs(os.path.join(os.getcwd(), "instances"), exist_ok=True)
    instances = [d for d in os.listdir(os.path.join(os.getcwd(), "instances")) if os.path.isdir(os.path.join(os.getcwd(), "instances", d))]
    instance_combo['values'] = instances
    if instances and not instance_var.get(): instance_combo.set(instances[0])
    show_content_list()

instance_combo.bind("<<ComboboxSelected>>", lambda e: show_content_list())
def open_generator():
    gen_win = tk.Toplevel(root); MCFullInstanceGenerator(gen_win); gen_win.bind("<Destroy>", lambda e: refresh_instances() if e.widget == gen_win else None)

tk.Button(top_frame, text="🛠 Neuer Generator", font=("Segoe UI", 14, "bold"), bg="#ff9800", fg="white", bd=0, command=open_generator).pack(side="left", padx=15)
start_button = tk.Button(root, text="Start", font=("Segoe UI", 22, "bold"), bg="#4CAF50", fg="white", width=20, bd=0, command=start_thread); start_button.pack(pady=15)
log_var = tk.BooleanVar(); tk.Checkbutton(root, text="Logs anzeigen", variable=log_var, command=toggle_logs, font=("Segoe UI", 16), bg="#121212", fg="white", selectcolor="#121212").pack()
tk.Button(root, text="➕ Add Content (Modrinth)", font=("Segoe UI", 16), bg="#3a8dde", fg="white", width=25, bd=0, command=open_modrinth_window).pack(pady=10)

content_canvas_frame = tk.Frame(root, bg="#1e1e1e")
c_canvas = tk.Canvas(content_canvas_frame, bg="#1e1e1e", highlightthickness=0); c_scroll = tk.Scrollbar(content_canvas_frame, orient="vertical", command=c_canvas.yview)
content_list_frame = tk.Frame(c_canvas, bg="#1e1e1e"); content_list_frame.bind("<Configure>", lambda e: c_canvas.configure(scrollregion=c_canvas.bbox("all")))
c_canvas.create_window((0, 0), window=content_list_frame, anchor="nw", width=800); c_canvas.configure(yscrollcommand=c_scroll.set)
c_canvas.pack(side="left", fill="both", expand=True); c_scroll.pack(side="right", fill="y")

log_box = tk.Text(root, bg="#1e1e1e", fg="white", font=("Consolas", 14), width=120, height=25, bd=0, state="disabled")
log_box.tag_config("red", foreground="red"); log_box.tag_config("yellow", foreground="yellow"); log_box.tag_config("lime", foreground="#00ff88")
tk.Button(root, text="📁 Ordner öffnen", font=("Segoe UI", 18), bg="#333333", fg="white", width=25, bd=0, command=open_folder).pack(pady=10)

refresh_instances()
root.mainloop()