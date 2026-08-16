document.addEventListener('alpine:init', () => {
    Alpine.data('collaboratorField', (isLocked) => ({
        isLocked: Boolean(isLocked),
        collabs: [],
        upsertCollaboratorOption(collaborator) {
            const selects = this.$root.querySelectorAll('select[name="collaborators_list"]');
            selects.forEach((select) => {
                const existingOption = Array.from(select.options).find((option) => option.value === String(collaborator.id));
                if (existingOption) {
                    existingOption.textContent = collaborator.name;
                    return;
                }

                const option = document.createElement('option');
                option.value = collaborator.id;
                option.textContent = collaborator.name;
                select.appendChild(option);
            });
        },
        handleCollaboratorSaved(event) {
            if (this.isLocked) {
                return;
            }
            const collaborator = event.detail || {};
            if (!collaborator.id || !collaborator.name) {
                return;
            }

            this.upsertCollaboratorOption(collaborator);

            const targetIndex = Number.parseInt(localStorage.getItem('budget_step3_collaborator_idx') || '-1', 10);
            if (targetIndex >= 0 && this.collabs[targetIndex]) {
                this.collabs[targetIndex].id = String(collaborator.id);
                this.collabs = [...this.collabs];
            }

            localStorage.removeItem('budget_step3_collaborator_idx');

            if (typeof form_modal !== 'undefined' && form_modal && form_modal.open) {
                form_modal.close();
            }
        },
        init() {
            if (!this.isLocked) {
                const root = this.$root && this.$root.closest ? this.$root.closest('#step-container') : null;
                if (root && root.dataset && root.dataset.budgetLocked === '1') {
                    this.isLocked = true;
                }
            }

            const rawData = this.$root.querySelector('#initial-collabs-data') || document.getElementById('initial-collabs-data');
            const data = rawData ? JSON.parse(rawData.textContent) : [];
            this.collabs = data.map((collaborator) => ({
                ...collaborator,
                _key: Date.now() + Math.random(),
            }));

            window.addEventListener('collaboratorSaved', this.handleCollaboratorSaved.bind(this));
        },
        addCollab() {
            if (this.isLocked) {
                return;
            }
            this.collabs.push({ id: '', is_new: true, _key: Date.now() + Math.random() });
        },
        removeCollab(index) {
            if (this.isLocked) {
                return;
            }
            this.collabs.splice(index, 1);
        },
        updateCollab(index, id) {
            if (this.isLocked) {
                return;
            }
            this.collabs[index].id = id;
        },
    }));
});
