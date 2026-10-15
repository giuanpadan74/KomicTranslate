from modules.gemini_response_js_state import get_copy_button_helpers_js


def _copy_button_helpers() -> str:
    return get_copy_button_helpers_js()


def get_js_copy_response_state() -> str:
    return f"""(function() {{{_copy_button_helpers()} return JSON.stringify(buildState(false)); }})();"""


def get_js_click_response_copy() -> str:
    return f"""
        (function() {{
            {_copy_button_helpers()}
            const state = buildState(true);
            if (!state.ready || !state.button) return JSON.stringify(state);
            state.button.scrollIntoView({{ block: 'center', inline: 'center' }});
            const methods = [];
            const normalizedLabels = (state.labels || []).join(' ');
            try {{ state.button.click(); methods.push('click'); }} catch (error) {{}}
            try {{
                state.button.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                methods.push('mouseevent');
            }} catch (error) {{}}
            if (normalizedLabels.includes('altro') || normalizedLabels.includes('more')) {{
                try {{
                    state.button.dispatchEvent(new MouseEvent('pointerdown', {{ bubbles: true, cancelable: true, view: window, buttons: 1 }}));
                    state.button.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window, buttons: 1 }}));
                    state.button.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true, view: window, buttons: 1 }}));
                    methods.push('open_menu_sequence');
                }} catch (error) {{}}
            }}
            const validation = buildState(false);
            return JSON.stringify({{
                status: methods.length ? 'clicked' : 'click_failed',
                ready: validation.ready,
                labels: state.labels,
                exact_response_match: state.exact_response_match,
                exact_prompt_match: state.exact_prompt_match,
                generic_copy_match: state.generic_copy_match,
                visible: validation.visible,
                enabled: validation.enabled,
                rendered: validation.rendered,
                in_response_container: state.in_response_container,
                associated_with_response: validation.associated_with_response,
                prompt_button_visible: validation.prompt_button_visible,
                prompt_button_count: validation.prompt_button_count,
                response_container_found: validation.response_container_found,
                image_menu_item_found: validation.image_menu_item_found,
                more_button_found: validation.more_button_found,
                post_click_valid: (
                    (
                        (state.exact_response_match || state.generic_copy_match)
                        && !state.exact_prompt_match
                        && validation.associated_with_response
                    )
                    || validation.image_menu_item_found
                    || (validation.ready && validation.labels && validation.labels.some(label => label.includes('copia immagine') || label.includes('copy image')))
                ),
                methods: methods
            }});
        }})();
    """
