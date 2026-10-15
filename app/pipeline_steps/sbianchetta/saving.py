"""
Salvataggio immagine pulita + immagine tradotta vuota per la sbianchetta.
"""
import os

import cv2

from app.ui.canvas.save_renderer import ImageSaveRenderer


def save_translated(pipeline, inpaint_input_img, blk_list, text_items_state,
                    image_path, archive_bname, timestamp, directory,
                    base_name, extension, export_settings) -> None:
    main_page = pipeline.main_page
    main_page.image_states[image_path]["viewer_state"].update(
        {"text_items_state": text_items_state}
    )
    main_page.image_states[image_path].update({"blk_list": blk_list})

    needs_workspace = (
        bool(archive_bname)
        or export_settings.get("export_inpainted_image", False)
        or export_settings.get("export_raw_text", False)
        or export_settings.get("export_translated_text", False)
    )
    if needs_workspace:
        render_save_dir = os.path.join(
            directory, f"comic_translate_{timestamp}",
            "translated_images", archive_bname,
        )
        os.makedirs(render_save_dir, exist_ok=True)
    else:
        # Nessun salvataggio automatico "<nome>_translated.<ext>" accanto
        # all'originale: senza archivio/export l'immagine resta nel canvas
        # e va esportata con il comando "Salva".
        render_save_dir = None

    im_bgr = cv2.cvtColor(inpaint_input_img, cv2.COLOR_RGB2BGR)
    renderer = ImageSaveRenderer(im_bgr)
    viewer_state = main_page.image_states[image_path]["viewer_state"]
    renderer.add_state_to_image(viewer_state)
    if render_save_dir and base_name and base_name != "_":
        sv_pth = os.path.join(
            render_save_dir, f"{base_name}_translated{extension}"
        )
        renderer.save_image(sv_pth)
        pipeline._register_saved_path(sv_pth)