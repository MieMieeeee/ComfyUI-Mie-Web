/* ComfyUI-Mie 短剧工作台 —— 前端逻辑。
 *
 * 纯浏览器脚本，没有构建步骤：Alpine 是 vendored 的一个文件。
 * appShell 是外壳（导航 + ComfyUI 状态），每个页面一个组件。
 */

const api = {
  async get(url) {
    const response = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  },
  async post(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `${response.status}`);
    return data;
  },
};

/* ------------------------------------------------------------------ */
/* 外壳                                                                 */
/* ------------------------------------------------------------------ */

function appShell() {
  return {
    currentTab: document.body.dataset.tab || "video",
    comfyStatusUrl: "",
    comfyOnline: false,
    comfyText: "检查中…",

    async init() {
      await this.refreshStatus();
    },

    async refreshStatus() {
      try {
        const data = await api.get("/api/comfy_status");
        this.comfyOnline = !!data.online;
        this.comfyStatusUrl = data.online ? data.url : "";
        if (data.online) {
          const device = (data.devices || [])[0];
          const vram = device && device.vram_total
            ? ` · 显存 ${Math.round(device.vram_free / 1e9)}/${Math.round(device.vram_total / 1e9)}G`
            : "";
          this.comfyText = `ComfyUI ${data.comfyui_version || ""}${vram}`;
        } else {
          this.comfyText = "ComfyUI 未连接";
        }
      } catch (error) {
        this.comfyOnline = false;
        this.comfyText = "ComfyUI 未连接";
      }
    },

    get comfyStatusShort() {
      return this.comfyOnline ? "已连接" : "未连接";
    },
    get comfyStatusClass() {
      return this.comfyOnline ? "ok" : "err";
    },
    get comfyStatusTitle() {
      return this.comfyText;
    },
  };
}

/* ------------------------------------------------------------------ */
/* 大模型                                                               */
/* ------------------------------------------------------------------ */

function llmPage() {
  return {
    platforms: [],
    current: "",
    keysFile: "",
    lastResult: "",

    async init() {
      await this.load();
    },

    async load() {
      try {
        const data = await api.get("/api/llm/platforms");
        this.platforms = data.platforms || [];
        this.current = data.current || "";
        this.keysFile = data.keys_file || "";
      } catch (error) {
        this.lastResult = `读取失败：${error.message}`;
      }
    },

    async saveKey(platform) {
      const input = document.querySelector(`input[data-key="${platform.key}"]`);
      const token = input ? input.value : "";
      try {
        const result = await api.post("/api/llm/key", { key: platform.key, token });
        platform.has_key = result.has_key;
        platform.key_masked = result.key_masked;
        this.lastResult = `${platform.name} 的 Key 已保存`;
      } catch (error) {
        this.lastResult = `保存失败：${error.message}`;
      }
    },

    async saveModel(platform) {
      try {
        await api.post("/api/llm/model", { key: platform.key, model: platform.model });
        this.lastResult = `${platform.name} 的模型已保存`;
      } catch (error) {
        this.lastResult = `保存失败：${error.message}`;
      }
    },

    async saveHost(platform) {
      const input = document.querySelector(`input[data-host="${platform.key}"]`);
      try {
        await api.post("/api/llm/host", { key: platform.key, host: input ? input.value : "" });
        this.lastResult = `${platform.name} 的地址已保存`;
      } catch (error) {
        this.lastResult = `保存失败：${error.message}`;
      }
    },

    async makeCurrent(platform) {
      try {
        await api.post("/api/llm/current", { key: platform.key });
        this.platforms.forEach((p) => { p.current = p.key === platform.key; });
        this.current = platform.key;
        this.lastResult = `当前平台：${platform.name}`;
      } catch (error) {
        this.lastResult = `切换失败：${error.message}`;
      }
    },

    async test(platform) {
      platform.busy = true;
      this.lastResult = `${platform.name} 测试中…`;
      try {
        const result = await api.post("/api/llm/test", {
          key: platform.key, model: platform.model,
        });
        this.lastResult = result.ok
          ? `${platform.name} 通了：${result.answer || "(空回答)"}`
          : `${platform.name} 失败：${result.error}`;
      } catch (error) {
        this.lastResult = `${platform.name} 失败：${error.message}`;
      } finally {
        platform.busy = false;
      }
    },
  };
}

/* ------------------------------------------------------------------ */
/* 角色与场景资产                                                        */
/* ------------------------------------------------------------------ */

function assetsPage() {
  return {
    kind: "character",
    payload: { characters: [], scenes: [], storyboards: [] },
    libraryDir: "",
    selected: "",
    detail: {},
    editing: false,
    form: { name: "", description: "", voice: "", ambience: "" },
    imageFile: null,
    audioFile: null,
    message: "",

    async init() {
      await this.load();
    },

    get items() {
      const list = this.kind === "character" ? this.payload.characters : this.payload.scenes;
      return (list || []).filter((x) => x && x.name);
    },

    async load() {
      try {
        this.payload = await api.get("/api/assets");
        this.libraryDir = this.payload.library_dir || "";
      } catch (error) {
        this.message = `读取失败：${error.message}`;
      }
    },

    async open(name) {
      this.selected = name;
      this.editing = false;
      this.message = "";
      try {
        this.detail = await api.get(`/api/assets/${this.kind}/${encodeURIComponent(name)}`);
      } catch (error) {
        this.detail = {};
        this.message = `读取失败：${error.message}`;
      }
    },

    startNew() {
      this.selected = "";
      this.detail = {};
      this.editing = true;
      this.imageFile = null;
      this.audioFile = null;
      this.form = { name: "", description: "", voice: "", ambience: "" };
      this.message = "";
    },

    startEdit() {
      this.editing = true;
      this.imageFile = null;
      this.audioFile = null;
      this.form = {
        name: this.detail.name || "",
        description: this.detail.description || "",
        voice: this.detail.voice || "",
        ambience: this.detail.ambience || "",
      };
    },

    cancel() {
      this.editing = false;
      this.imageFile = null;
      this.audioFile = null;
    },

    pickImage(event) {
      this.imageFile = event.target.files[0] || null;
    },

    pickAudio(event) {
      this.audioFile = event.target.files[0] || null;
    },

    async save() {
      const body = new FormData();
      body.append("name", this.form.name || "");
      body.append("description", this.form.description || "");
      if (this.kind === "character") {
        body.append("voice", this.form.voice || "");
      } else {
        body.append("ambience", this.form.ambience || "");
      }
      if (this.imageFile) body.append("image", this.imageFile);
      if (this.audioFile) body.append("audio", this.audioFile);
      try {
        const response = await fetch(`/api/assets/${this.kind}`, {
          method: "POST", body,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || response.statusText);
        this.message = `已保存：${data.name}（${data.status}）`;
        this.editing = false;
        await this.load();
        await this.open(data.name);
      } catch (error) {
        this.message = `保存失败：${error.message}`;
      }
    },

    async remove() {
      if (!this.selected) return;
      if (!window.confirm(`删除 ${this.selected}？`)) return;
      try {
        await api.post(`/api/assets/${this.kind}/${encodeURIComponent(this.selected)}/delete`);
        this.selected = "";
        this.detail = {};
        this.message = "已删除";
        await this.load();
      } catch (error) {
        this.message = `删除失败：${error.message}`;
      }
    },
  };
}

/* ------------------------------------------------------------------ */
/* 剧本资产                                                             */
/* ------------------------------------------------------------------ */

function scriptsPage() {
  return {
    names: [],
    selected: "",
    raw: "",
    preview: "",
    errors: [],
    warnings: [],
    okMessage: "",

    async init() {
      await this.load();
    },

    async load() {
      try {
        const data = await api.get("/api/scripts");
        this.names = data.names || [];
      } catch (error) {
        this.okMessage = `读取失败：${error.message}`;
      }
    },

    async open(name) {
      this.selected = name;
      this.errors = []; this.warnings = []; this.okMessage = "";
      try {
        const data = await api.get(`/api/scripts/${encodeURIComponent(name)}`);
        this.raw = JSON.stringify(data.json, null, 2);
        this.preview = data.preview || "";
        await this.validate();
      } catch (error) {
        this.okMessage = `读取失败：${error.message}`;
      }
    },

    startNew() {
      this.selected = "";
      this.errors = []; this.warnings = []; this.okMessage = "";
      this.preview = "";
      this.raw = JSON.stringify({
        version: 2, name: "新剧本", language: "zh",
        roles: [{
          id: "character_1", name: "角色1", presence: "on_screen",
          initially_visible: true, position: "center", voice: "",
        }],
        camera: { framing: "medium_close_up", movement: "locked", perspective: "observer" },
        look: "", setting: "",
        constraints: "",
        // Two seconds: the contract rejects a target that is much longer
        // than the events need ("too long for the event density"), and a
        // skeleton with one short line is exactly that.
        target_duration_seconds: 2, continuation_overlap_frames: 0,
        source_script: "角色1：你好",
        shots: [{
          id: "scene_01", duration_seconds: 5,
          events: [{ id: "event_001", type: "dialogue", character: "character_1",
                     text: "你好", language: "zh" }],
        }],
        execution: {
          look: "", setting: "", visible_state: "Character 1 stands at center.",
          voices: { character_1: "" }, directions: {},
        },
        audio_mode: "generated",
      }, null, 2);
    },

    async validate() {
      try {
        const result = await api.post("/api/scripts/validate", { json: this.raw });
        this.errors = result.errors || [];
        this.warnings = result.warnings || [];
        this.okMessage = result.ok ? "契约通过" : "";
      } catch (error) {
        this.errors = [error.message];
        this.okMessage = "";
      }
    },

    async save() {
      try {
        const result = await api.post("/api/scripts", { json: this.raw });
        this.selected = result.name;
        this.preview = result.preview || "";
        this.okMessage = `已保存：${result.name}（${result.status}）`;
        this.errors = []; this.warnings = [];
        await this.load();
      } catch (error) {
        this.errors = [error.message];
      }
    },

    async remove() {
      if (!this.selected) return;
      if (!window.confirm(`删除 ${this.selected}？`)) return;
      try {
        await api.post(`/api/scripts/${encodeURIComponent(this.selected)}/delete`);
        this.selected = ""; this.raw = ""; this.preview = "";
        this.okMessage = "已删除";
        await this.load();
      } catch (error) {
        this.okMessage = `删除失败：${error.message}`;
      }
    },
  };
}

/* ------------------------------------------------------------------ */
/* 视频制作                                                             */
/* ------------------------------------------------------------------ */

function videoPage() {
  return {
    scripts: [],
    characters: [],
    script: "",
    roles: [],
    runName: "",
    width: 960,
    height: 544,
    steps: 20,
    duration: 18,
    jobs: [],
    planPreview: "",
    message: "",
    statusText: "",

    async init() {
      await this.loadScripts();
      await this.refreshJobs();
    },

    async loadScripts() {
      try {
        const data = await api.get("/api/scripts");
        this.scripts = data.names || [];
        const assets = await api.get("/api/assets");
        this.characters = (assets.characters || [])
          .filter((x) => x && x.name).map((x) => x.name);
      } catch (error) {
        this.message = `读取失败：${error.message}`;
      }
    },

    async loadScript() {
      this.roles = [];
      this.planPreview = "";
      this.message = "";
      if (!this.script) return;
      try {
        const data = await api.get(`/api/scripts/${encodeURIComponent(this.script)}`);
        this.roles = (data.json.roles || []).map((r) => ({
          id: r.id, name: r.name, presence: r.presence, asset: "",
        }));
        await this.preview();
      } catch (error) {
        this.message = `读取失败：${error.message}`;
      }
    },

    roleAssets() {
      const out = {};
      this.roles.forEach((r) => { if (r.asset) out[r.id] = r.asset; });
      return out;
    },

    async preview() {
      if (!this.script || !this.roles.length) return;
      // The assembler refuses a slot with no asset, so there is nothing to
      // preview until every role has one. Asking anyway would just produce
      // an error the user cannot act on yet.
      if (this.roles.some((r) => !r.asset)) {
        this.planPreview = "";
        return;
      }
      try {
        const data = await api.post(
          `/api/scripts/${encodeURIComponent(this.script)}/plan`,
          { role_assets: this.roleAssets() });
        this.planPreview = (data.requirements || [])
          .map((r) => `${r.socket}: ${r.kind} ${r.name || "(未接线)"}`
            + `${r.required ? " [必填]" : ""}${r.note ? " — " + r.note : ""}`)
          .join("\n");
      } catch (error) {
        this.planPreview = "";
      }
    },

    async submit() {
      this.message = "提交中…";
      try {
        const record = await api.post("/api/render/submit", {
          script: this.script,
          role_assets: this.roleAssets(),
          run_name: this.runName,
          width: this.width, height: this.height,
          steps: this.steps, duration: this.duration,
        });
        this.message = `已排队（#${record.number}），渲染要几分钟`;
        await this.refreshJobs();
      } catch (error) {
        this.message = `提交失败：${error.message}`;
      }
    },

    async refreshJobs() {
      try {
        const data = await api.get("/api/render/jobs");
        this.jobs = data.jobs || [];
        this.statusText = this.jobs.length
          ? `${this.jobs.length} 个任务`
          : "";
      } catch (error) {
        this.statusText = "";
      }
    },
  };
}
