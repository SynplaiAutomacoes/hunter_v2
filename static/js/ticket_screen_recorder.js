(function () {
  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  window.ticketAttachments = function ticketAttachments(options) {
    const maxBytes = Number(options?.maxBytes || 300 * 1024 * 1024);
    const maxSeconds = Number(options?.maxSeconds || 300);

    return {
      fileNames: [],
      isRecording: false,
      recordingBusy: false,
      recordingLabel: "",
      mediaRecorder: null,
      recordedChunks: [],
      recordingTimer: null,
      displayStream: null,
      micStream: null,

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
        await this.startRecording();
      },

      async startRecording() {
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
          this.recordingLabel = "Gravando...";

          this.recordingTimer = window.setTimeout(() => {
            if (this.isRecording) {
              this.stopRecording();
              alert("A gravação atingiu o limite de 5 minutos e foi finalizada.");
            }
          }, maxSeconds * 1000);

          this.displayStream.getVideoTracks()[0]?.addEventListener("ended", () => {
            if (this.isRecording) this.stopRecording();
          });
        } catch (err) {
          console.error(err);
          this.recordingLabel = "Não foi possível iniciar a gravação.";
          this.cleanupStreams();
        } finally {
          this.recordingBusy = false;
        }
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
  };
})();
