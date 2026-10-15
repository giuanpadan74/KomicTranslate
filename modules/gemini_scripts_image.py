import json


def get_js_paste_image() -> str:
    """Inietta immagine dalla clipboard usando execCommand paste."""
    return '''
        (function() {
            try {
                document.execCommand('paste');
                return true;
            } catch(e) {
                console.log('[GVB] Paste failed:', e);
                return false;
            }
        })();
    '''


def get_js_check_image_uploaded() -> str:
    """Verifica se un'immagine è stata caricata nell'input."""
    return '''
        (function() {
            const fileInput = document.querySelector('input[type="file"]');
            if (fileInput && fileInput.files && fileInput.files.length > 0) {
                return true;
            }
            const imgPreviews = document.querySelectorAll('img[src*="blob"], img[src*="data:image"]');
            return imgPreviews.length > 0;
        })();
    '''


def get_js_find_file_input() -> str:
    """Trova e restituisce l'input file per l'upload."""
    return '''
        (function() {
            const fileInput = document.querySelector('input[type="file"]');
            if (fileInput) {
                return 'found';
            }
            const attachBtn = document.querySelector('button[aria-label*="Allega"]') ||
                              document.querySelector('button[aria-label*="Attach"]') ||
                              document.querySelector('button[aria-label*="Aggiungi"]') ||
                              document.querySelector('button[aria-label*="Add"]') ||
                              document.querySelector('[data-testid="attach-button"]');
            if (attachBtn) {
                return 'button_found';
            }
            return 'not_found';
        })();
    '''


def get_js_click_attach_and_upload(file_path_js: str) -> str:
    """Clicca sul pulsante attachment e passa il file."""
    return f'''
        (function() {{
            const attachBtn = document.querySelector('button[aria-label*="Allega"]') ||
                              document.querySelector('button[aria-label*="Attach"]') ||
                              document.querySelector('button[aria-label*="Aggiungi"]') ||
                              document.querySelector('button[aria-label*="Add"]') ||
                              document.querySelector('[data-testid="attach-button"]') ||
                              document.querySelector('button:has(mat-icon[svgicon*="attach"])') ||
                              document.querySelector('button:has(mat-icon[svgicon*="add_photo"])') ||
                              document.querySelector('button mat-icon[svgicon*="attach"]')?.closest('button');
            
            if (attachBtn && !attachBtn.disabled) {{
                attachBtn.click();
                setTimeout(() => {{
                    const fileInput = document.querySelector('input[type="file"]');
                    if (fileInput) {{
                        const dataTransfer = new DataTransfer();
                        const file = {file_path_js};
                        if (file) {{
                            dataTransfer.items.add(file);
                            fileInput.files = dataTransfer.files;
                            fileInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            console.log('[GVB] File added to input');
                        }}
                    }}
                }}, 500);
                return true;
            }}
            return false;
        }})();
    '''


def get_js_check_image_loaded() -> str:
    """Verifica se l'immagine è visibile nella chat (caricamento completato)."""
    return '''
        (function() {
            const imgs = document.querySelectorAll('.chat-image img, img[src*="blob"]');
            const attachedImgs = document.querySelectorAll('[data-testid="image-attachment"] img');
            const uploadingIndicator = document.querySelector('[data-testid="uploading-image"], .uploading-image');
            
            if (uploadingIndicator) {
                return 'uploading';
            }
            
            if (imgs.length > 0 || attachedImgs.length > 0) {
                return 'loaded';
            }
            
            const imgContainers = document.querySelectorAll('.message-image, .attachment-image');
            return imgContainers.length > 0 ? 'loaded' : 'not_found';
        })();
    '''


def get_js_has_pending_image() -> str:
    """Verifica se c'è un'immagine in attesa di invio."""
    return '''
        (function() {
            const uploading = document.querySelector('[data-testid="uploading-image"]');
            const pending = document.querySelector('.pending-image, [data-testid="pending-attachment"]');
            return uploading ? 'uploading' : (pending ? 'pending' : 'none');
        })();
    '''


def get_js_get_image_upload_state() -> str:
    return '''
        (function() {
            const uploading = document.querySelector('[data-testid="uploading-image"], .uploading-image, [class*="upload"][class*="progress"]');
            const pending = document.querySelector('.pending-image, [data-testid="pending-attachment"], [class*="pending"][class*="image"]');
            const previews = document.querySelectorAll('img[src*="blob"], img[src*="data:image"], [data-testid="image-attachment"] img');
            const fileInput = document.querySelector('input[type="file"]');
            const state = {
                status: 'none',
                previewFound: previews.length > 0,
                uploadingFound: !!uploading,
                pendingFound: !!pending,
                fileInputFound: !!fileInput,
            };
            if (uploading) {
                state.status = 'uploading';
            } else if (previews.length > 0) {
                state.status = 'loaded';
            } else if (pending) {
                state.status = 'pending';
            }
            return JSON.stringify(state);
        })();
    '''
