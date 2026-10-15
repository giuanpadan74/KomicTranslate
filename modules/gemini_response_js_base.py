def get_copy_button_base_js() -> str:
    return """
            const RESPONSE_LABEL_KEYWORDS = [
                'copia risposta',
                'copy response',
                'copia codice',
                'copy code',
                'copia risultato',
                'copy result',
                'copia immagine',
                'copy image'
            ];
            const PROMPT_LABEL_KEYWORDS = ['copia prompt', 'copy prompt'];
            const COPY_ICON_KEYWORDS = ['copy', 'content_copy', 'copia'];
            const CODE_BLOCK_SELECTORS = ['pre', 'code', '[class*="code"]', '[data-testid*="code"]'];
            const RESPONSE_SELECTORS = [
                'button[aria-label="Copia risposta"]',
                'button[aria-label="Copy response"]',
                'button[aria-label="Copia codice"]',
                'button[aria-label="Copy code"]',
                'button[aria-label="Copia risultato"]',
                'button[aria-label="Copy result"]',
                'button[aria-label*="Copia risposta"]',
                'button[aria-label*="Copy response"]',
                'button[aria-label*="Copia codice"]',
                'button[aria-label*="Copy code"]',
                'button[aria-label*="Copia risultato"]',
                'button[aria-label*="Copy result"]',
                'button[mattooltip*="Copia risposta"]',
                'button[mattooltip*="Copy response"]',
                'button[mattooltip*="Copia codice"]',
                'button[mattooltip*="Copy code"]',
                'button[mattooltip*="Copia risultato"]',
                'button[mattooltip*="Copy result"]',
                'button[data-test*="copy-response"]',
                'button[data-testid*="copy-response"]',
                'button[data-test*="copy-code"]',
                'button[data-testid*="copy-code"]',
                'button[data-test*="copy-result"]',
                'button[data-testid*="copy-result"]',
                'button[aria-label*="Copia immagine"]',
                'button[aria-label*="Copy image"]',
                'button[mattooltip*="Copia immagine"]',
                'button[mattooltip*="Copy image"]',
                'button[data-test*="copy-image"]',
                'button[data-testid*="copy-image"]',
                '[role="menuitem"]',
                '[role="menuitemradio"]',
                '[role="option"]'
            ];
            const RESPONSE_CONTAINERS = [
                '[data-testid="response-container"]',
                '[data-response-id]',
                'model-response',
                '.response-container',
                '.message-content',
                '.markdown'
            ];

            function normalizeLabel(value) {
                return String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            }

            function matchesLabel(label, keywords) {
                if (!label) return false;
                return keywords.some(keyword => label === keyword || label.includes(keyword));
            }

            function matchesResponseLabel(label) {
                return matchesLabel(label, RESPONSE_LABEL_KEYWORDS);
            }

            function matchesPromptLabel(label) {
                return matchesLabel(label, PROMPT_LABEL_KEYWORDS);
            }

            function collectLabels(button) {
                const icon = button?.querySelector('mat-icon, [data-icon], svg, i, span');
                return [
                    button?.getAttribute('aria-label'),
                    button?.getAttribute('mattooltip'),
                    button?.getAttribute('title'),
                    button?.getAttribute('data-test'),
                    button?.getAttribute('data-testid'),
                    button?.getAttribute('aria-description'),
                    button?.getAttribute('data-tooltip'),
                    icon?.getAttribute?.('svgicon'),
                    icon?.getAttribute?.('data-icon'),
                    icon?.getAttribute?.('aria-label'),
                    button?.innerText,
                    button?.textContent
                ].map(normalizeLabel).filter(Boolean);
            }

            function hasCopyIcon(button) {
                if (!button) return false;
                const nodes = [button, ...button.querySelectorAll('mat-icon, [data-icon], svg, i, span')];
                return nodes.some(node => {
                    const hints = [
                        node?.getAttribute?.('svgicon'),
                        node?.getAttribute?.('data-icon'),
                        node?.getAttribute?.('aria-label'),
                        node?.getAttribute?.('title'),
                        node?.textContent
                    ].map(normalizeLabel).filter(Boolean);
                    return hints.some(label => COPY_ICON_KEYWORDS.some(keyword => label.includes(keyword)));
                });
            }

            function isVisible(element) {
                if (!element || !element.isConnected) return false;
                const style = window.getComputedStyle(element);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                if (style.pointerEvents === 'none') return false;
                const rect = element.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }

            function isEnabled(element) {
                return !!element && !element.disabled && element.getAttribute('aria-disabled') !== 'true';
            }

            function isRendered(element) {
                if (!isVisible(element)) return false;
                const rect = element.getBoundingClientRect();
                return rect.top < window.innerHeight && rect.bottom > 0;
            }

            function isAssociatedWithResponse(button, responseContainer) {
                if (!button || !responseContainer) return false;
                if (responseContainer.contains(button)) return true;
                const parent = responseContainer.parentElement;
                if (parent && parent.contains(button)) return true;
                const buttonRect = button.getBoundingClientRect();
                const responseRect = responseContainer.getBoundingClientRect();
                return Math.abs(buttonRect.top - responseRect.bottom) <= 220;
            }

            function findLatestResponseContainer() {
                const containers = [];
                for (const selector of RESPONSE_CONTAINERS) {
                    for (const element of document.querySelectorAll(selector)) {
                        if (isVisible(element)) containers.push(element);
                    }
                }
                const latest = containers.length ? containers[containers.length - 1] : null;
                if (latest) {
                    try {
                        latest.scrollIntoView({ block: 'end', inline: 'nearest' });
                        latest.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, cancelable: true, view: window }));
                        latest.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, cancelable: true, view: window }));
                    } catch (error) {}
                }
                return latest;
            }

            function responseHasUsefulContent(responseContainer) {
                if (!responseContainer) return false;
                const text = normalizeLabel(responseContainer.innerText || '');
                if (text.includes('block_1') || text.includes('"id"') || text.includes('"it"') || text.includes('```json')) {
                    return true;
                }
                return CODE_BLOCK_SELECTORS.some(selector => responseContainer.querySelector(selector));
            }
    """
