(function (root) {
    'use strict';

    function createController({ fields = {}, callbacks = {} } = {}) {
        const {
            closeProvision = () => {},
            saveProvision = () => {},
            closeCredentials = () => {},
            saveCredentials = () => {},
            closeTrust = () => {},
            previewTrust = () => {},
            saveTrust = () => {},
            verifyTrust = () => {},
            deleteTrust = () => {},
            trustCertificateSelected = () => {},
            trustFingerprintChanged = () => {},
            closeEdit = () => {},
            saveEdit = () => {},
        } = callbacks;

        function addListener(fieldName, eventName, callback) {
            if (fields[fieldName]) fields[fieldName].addEventListener(eventName, callback);
        }

        function bind() {
            addListener('closeProvision', 'click', closeProvision);
            addListener('cancelProvision', 'click', closeProvision);
            addListener('saveProvision', 'click', saveProvision);
            addListener('closeCredentials', 'click', closeCredentials);
            addListener('cancelCredentials', 'click', closeCredentials);
            addListener('saveCredentials', 'click', saveCredentials);
            addListener('closeTrust', 'click', closeTrust);
            addListener('cancelTrust', 'click', closeTrust);
            addListener('previewTrust', 'click', previewTrust);
            addListener('saveTrust', 'click', saveTrust);
            addListener('verifyTrust', 'click', verifyTrust);
            addListener('deleteTrust', 'click', deleteTrust);
            addListener('trustCertificate', 'change', trustCertificateSelected);
            addListener('trustFingerprint', 'change', trustFingerprintChanged);
            addListener('closeEdit', 'click', closeEdit);
            addListener('cancelEdit', 'click', closeEdit);
            addListener('saveEdit', 'click', saveEdit);
        }

        return Object.freeze({ bind });
    }

    root.LabManagerModalBindings = Object.freeze({ createController });
})(window);
