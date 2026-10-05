document.addEventListener("alpine:init", () => {
  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  Alpine.data("ticketAttachments", (options = {}) => {
    const maxBytes = Number(options.maxBytes || 300 * 1024 * 1024);
    const maxSeconds = Number(options.maxSeconds || 300);
    const countdownFrom = Number(options.countdownFrom || 3);

    return {
      fileNames: [],
      isRecording: false,
      recordingBusy: false,
      countdownSeconds: 0,
      recordingLabel: "",
      mediaRecorder: null,
      recordedChunks: [],
      recordingTimer: null,
      countdownTimer: null,
      countdownResolve: null,
      displayStream: null,
      micStream: null,

      get isCountingDown() {
        return this.countdownSeconds > 0;
      },

      get buttonIcon() {
        if (this.isRecording) return "stop";
        if (this.isCountingDown) return "timer";
        return "videocam";
      },

      get buttonLabel() {
        if (this.isRecording) return "Parar gravação";
        if (this.isCountingDown) return "Cancelar preparação";
        return "Gravar tela";
      },

      onFilesSelected(event) {
        const files = Array.from(event.target.files || []);
        this.fileNames = files.map((file) => `${file.name} (${formatBytes(file.size)})`);
        for (const file of files) {
          if (file.size > maxBytes) {
            alert(`O arquivo ${file.name} excede o limite de ${formatBytes(maxBytes)}.`);
            event.target.value = "";
            this.fileNames = [];
            return;
          }
        }
      },

      async toggleRecording() {
        if (this.isRecording) {
          this.stopRecording();
          return;
        }
        if (this.isCountingDown) {
          this.cancelCountdown({ label: "Preparação cancelada." });
          return;
        }
        await this.beginRecordingFlow();
      },

      async beginRecordingFlow() {
        this.recordingBusy = true;
        this.recordingLabel = "Solicitando permissão de tela e microfone...";
        try {
          this.displayStream = await navigator.mediaDevices.getDisplayMedia({
            video: true,
            audio: true,
          });
          try {
            this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          } catch (_err) {
            this.micStream = null;
          }

          this.recordingBusy = false;
          const shouldStart = await this.runCountdown();
          if (!shouldStart || !this.displayStream) {
            return;
          }
          this.startMediaRecorder();
        } catch (err) {
          console.error(err);
          this.recordingLabel = "Não foi possível iniciar a gravação.";
          this.cleanupStreams();
          this.recordingBusy = false;
        }
      },

      runCountdown() {
        return new Promise((resolve) => {
          this.countdownResolve = resolve;
          this.countdownSeconds = countdownFrom;
          this.recordingLabel = `Gravação inicia em ${this.countdownSeconds}…`;

          this.countdownTimer = window.setInterval(() => {
            this.countdownSeconds -= 1;
            if (this.countdownSeconds > 0) {
              this.recordingLabel = `Gravação inicia em ${this.countdownSeconds}…`;
              return;
            }

            window.clearInterval(this.countdownTimer);
            this.countdownTimer = null;
            this.countdownSeconds = 0;
            this.recordingLabel = "Iniciando gravação…";
            const done = this.countdownResolve;
            this.countdownResolve = null;
            if (done) done(true);
          }, 1000);
        });
      },

      cancelCountdown({ label } = {}) {
        if (this.countdownTimer) {
          window.clearInterval(this.countdownTimer);
          this.countdownTimer = null;
        }
        this.countdownSeconds = 0;
        this.cleanupStreams();
        this.recordingBusy = false;
        this.recordingLabel = label || "";
        const done = this.countdownResolve;
        this.countdownResolve = null;
        if (done) done(false);
      },

      startMediaRecorder() {
        const tracks = [...this.displayStream.getTracks()];
        if (this.micStream) {
          tracks.push(...this.micStream.getAudioTracks());
        }
        const combined = new MediaStream(tracks);
        this.recordedChunks = [];
        const candidates = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
        let recorder = null;
        for (const mimeType of candidates) {
          if (MediaRecorder.isTypeSupported && !MediaRecorder.isTypeSupported(mimeType)) continue;
          try {
            recorder = new MediaRecorder(combined, { mimeType });
            break;
          } catch (_err) {
            recorder = null;
          }
        }
        if (!recorder) {
          recorder = new MediaRecorder(combined);
        }
        this.mediaRecorder = recorder;
        this.mediaRecorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) {
            this.recordedChunks.push(event.data);
          }
        };
        this.mediaRecorder.onstop = () => this.onRecordingStop();
        this.mediaRecorder.start(1000);
        this.isRecording = true;
        this.recordingLabel = "Gravando…";

        this.recordingTimer = window.setTimeout(() => {
          if (this.isRecording) {
            this.stopRecording();
            alert("A gravação atingiu o limite de 5 minutos e foi finalizada.");
          }
        }, maxSeconds * 1000);

        this.displayStream.getVideoTracks()[0]?.addEventListener("ended", () => {
          if (this.isRecording) this.stopRecording();
          if (this.countdownSeconds > 0) this.cancelCountdown({ label: "Compartilhamento de tela encerrado." });
        });
      },

      stopRecording() {
        if (!this.mediaRecorder || this.mediaRecorder.state === "inactive") {
          this.isRecording = false;
          return;
        }
        this.mediaRecorder.stop();
        this.isRecording = false;
        if (this.recordingTimer) {
          window.clearTimeout(this.recordingTimer);
          this.recordingTimer = null;
        }
      },

      onRecordingStop() {
        const blob = new Blob(this.recordedChunks, { type: "video/webm" });
        this.cleanupStreams();
        if (blob.size > maxBytes) {
          this.recordingLabel = "Gravação excede 300 MB e foi descartada.";
          return;
        }
        const file = new File([blob], `gravacao-tela-${Date.now()}.webm`, { type: "video/webm" });
        const transfer = new DataTransfer();
        transfer.items.add(file);
        if (this.$refs.screenInput) {
          this.$refs.screenInput.files = transfer.files;
        }
        this.fileNames = [`${file.name} (${formatBytes(file.size)})`, ...this.fileNames];
        this.recordingLabel = "Gravação anexada automaticamente.";
      },

      cleanupStreams() {
        for (const stream of [this.displayStream, this.micStream]) {
          if (!stream) continue;
          for (const track of stream.getTracks()) track.stop();
        }
        this.displayStream = null;
        this.micStream = null;
      },
    };
  });
});
