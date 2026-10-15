# Controller Refactoring Plan

## Overview
Decompose `controller.py` (4534 lines, 167 methods) into three sub-controllers:
- `BatchController` – batch processing & progress
- `UIController` – text-item/rectangle UI interactions, text formatting, tools
- `ProjectController` – project save/load, image state management

## Architecture
```
ComicTranslate (controller.py)
├── inherits ComicTranslateUI (main_window.py)
├── delegates to BatchController (batch_controller.py)
├── delegates to UIController (ui_controller.py)
└── delegates to ProjectController (project_controller.py)
```

Each sub-controller receives a reference to the main `ComicTranslate` instance (`self.app`)
and accesses shared state through it.

## Method Assignment

### BatchController (batch_controller.py)
- `start_batch_process`
- `on_batch_process_finished`
- `on_semi_auto_batch_finished`
- `_delayed_reset_translate_flag`
- `_safety_timeout_handler`
- `_check_existing_blocks_batch`
- `_sync_blocks_with_ui`
- `update_progress`
- `_force_hide_progress_bar`
- `clear_rectangles_all_pages`
- `on_image_processed`
- `on_image_skipped`
- `_on_all_images_visually_updated`

### UIController (ui_controller.py)
- `connect_ui_elements`
- `highlight_button` / `clear_all_highlights`
- `connect_rect_item_signals` / `connect_text_item_signals`
- `on_text_item_selected` / `on_text_item_deselcted`
- `update_text_block_from_item` / `update_text_block_from_edit`
- `remove_newlines_from_target`
- `delete_selected_box`
- `get_selected_blocks` / `clear_multi_selection` / `update_ui_for_multi_selection`
- `apply_bold_to_selected` / `apply_italic_to_selected` / `apply_underline_to_selected`
- `apply_color_to_selected` / `apply_font_to_selected` / `apply_font_size_to_selected`
- `apply_alignment_to_selected` / `apply_line_spacing_to_selected` / `apply_outline_to_selected`
- `on_font_dropdown_change` / `on_font_size_change` / `on_line_spacing_change`
- `on_font_color_change` / `on_outline_color_change` / `on_outline_width_change`
- `left_align` / `center_align` / `right_align`
- `bold` / `italic` / `underline`
- `toggle_outline_settings`
- `block_text_item_widgets` / `unblock_text_item_widgets`
- `color_to_string`
- `set_values_for_blk_item` / `set_values_from_highlight`
- `handle_rectangle_selection` / `handle_rectangle_creation` / `handle_rectangle_deletion`
- `handle_rectangle_change` / `rect_change_undo`
- `on_blk_rendered`
- `clear_text_edits`
- `disable_hbutton_group` / `enable_hbutton_group`
- `display_image`
- `navigate_images`
- `update_image_cards` / `on_card_selected`
- `display_image_from_loaded` / `set_cv2_image`
- `show_txt_modal` / `show_txt_in_modal`
- `update_text_block`
- `show_original_image`
- `detect_fonts` / `_on_font_list_update_requested`
- `auto_center_text`

### ProjectController (project_controller.py)
- `save_image_state` / `save_current_image_state`
- `load_image_state`
- `load_initial_image` / `load_image` / `thread_load_images`
- `thread_insert`
- `on_initial_image_loaded`
- `clear_state` / `clear_all_items_new`
- `handle_image_deletion`
- `save_current_image` / `save_and_make` / `save_and_make_worker`
- `launch_save_proj_dialog` / `_get_suggested_filename`
- `run_save_proj` / `save_project` / `save_project_new` / `save_project_all_images`
- `thread_save_project` / `thread_save_as_project`
- `_is_batch_safe_for_save` / `show_save_choice_dialog`
- `create_text_items_from_data` / `update_ui_from_project`
- `thread_load_project` / `load_project` / `load_project_new`
- `_load_single_image_project` / `_load_multi_image_project`
- `rebuild_scene_after_load` / `log_object_state`
- `join_ctpr_files`
- `export_to_pdf`

### Remaining in ComicTranslate (controller.py)
- `__init__` (creates sub-controllers, initializes shared state)
- `push_command`
- `ocr` / `ocr_with_color`
- `translate_image`
- `inpaint_and_set`
- `block_detect`
- `finish_ocr_translate`
- `batch_mode_selected` / `manual_mode_selected`
- `on_manual_finished` / `on_block_detect_finished` / `on_ocr_finished`  
  `on_translate_finished` / `on_segmentation_finished` / `on_inpaint_finished`
- `run_threaded` / `cancel_current_task` / `default_error_handler`
- `render_text` / `on_render_complete`
- `blk_detect_segment` / `load_segmentation_points`
- `find_corresponding_text_block` / `find_corresponding_rect`
- `save_src_trg` / `set_src_trg_all`
- `change_all_blocks_size`
- `render_settings` / `process_group`
- `save_main_page_settings` / `load_main_page_settings`
- `closeEvent` / `keyPressEvent`
- `get_app_settings`
- `set_inpainter_model` / `refresh_inpainter_models` / `initialize_inpainter_models`
- `_on_inpainter_dropdown_changed`
