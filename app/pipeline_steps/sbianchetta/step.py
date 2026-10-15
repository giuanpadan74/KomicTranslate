"""
Orchestratore del processo batch 'Sbianchetta'.
Ricalca la logica della versione OLD, modularizzando le fasi in moduli separati.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime

import cv2

from modules.logging.auto_logger import (
    log_batch_operation,
    log_encoding_error,
)

from .blocks import _ensure_image_state, get_blk_list
from .inpainting import ensure_inpainter, inpaint
from .rendering import render_text_items
from .saving import save_translated

logger = logging.getLogger(__name__)


def _repack_archives(main_page, timestamp: str, total_images: int) -> None:
    """Ricostruisce gli archivi (CBZ/ZIP) finali dopo la sbianchetta."""
    archive_info_list = main_page.file_handler.archive_info
    if not archive_info_list:
        return

    save_as_settings = main_page.settings_page.get_export_settings().get(
        "save_as", {},
    )
    from modules.utils.archives import make

    for archive_index, archive in enumerate(archive_info_list):
        archive_index_input = total_images + archive_index
        main_page.progress_update.emit(
            archive_index_input, total_images, 1, 3, True,
        )
        archive_path = archive["archive_path"]
        archive_ext = os.path.splitext(archive_path)[1]
        archive_bname = os.path.splitext(
            os.path.basename(archive_path)
        )[0]
        archive_directory = os.path.dirname(archive_path)
        save_as_ext = f".{save_as_settings.get(archive_ext.lower(), 'zip')}"

        save_dir = os.path.join(
            archive_directory, f"comic_translate_{timestamp}",
            "translated_images", archive_bname,
        )
        check_from = os.path.join(
            archive_directory, f"comic_translate_{timestamp}",
        )
        main_page.progress_update.emit(
            archive_index_input, total_images, 2, 3, True,
        )

        output_base_name = f"{archive_bname}"
        output_path = os.path.join(
            archive_directory, f"{output_base_name}{save_as_ext}",
        )
        make(check_from, output_path, save_as_settings)

        main_page.progress_update.emit(
            archive_index_input, total_images, 3, 3, True,
        )


def sbianchetta_batch_process(pipeline, existing_blk_list=None,
                              skip_detection: bool = False) -> bool:
    """
    Entry-point eseguito nel thread pool.
    Sbianca i balloon di tutte le immagini caricate senza OCR né traduzione.
    """
    main_page = pipeline.main_page
    timestamp = datetime.now().strftime("%b-%d-%Y_%I-%M-%S%p")
    pipeline._last_batch_timestamp = timestamp
    pipeline._last_run_dirs = set()
    total_images = len(main_page.image_files)

    log_batch_operation("sbianchetta_start", total_images, 0, 0, 0.0)
    logger.info(
        "[SBIANCHETTA] Avvio processo sbianchetta per %s immagini",
        total_images,
    )
    start_time = time.time()

    for index, image_path in enumerate(main_page.image_files):
        if pipeline._check_batch_cancellation():
            pipeline._handle_batch_cancelled(total_images, index)
            return False

        _ensure_image_state(main_page, image_path)
        main_page.progress_update.emit(index, total_images, 0, 10, True)
        settings_page = main_page.settings_page
        # Il dropdown (via snapshot GUI-thread-safe) e' l'unica fonte di
        # verita': lo stato salvato puo' contenere una lingua obsoleta.
        source_lang = pipeline._ui_source_lang()
        target_lang = pipeline._ui_target_lang()
        main_page.image_states[image_path]["source_lang"] = source_lang
        main_page.image_states[image_path]["target_lang"] = target_lang
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        extension = os.path.splitext(image_path)[1]
        directory = os.path.dirname(image_path)
        pipeline._last_run_dirs.add(directory)

        archive_bname = ""
        for archive in main_page.file_handler.archive_info:
            if image_path in archive.get("extracted_images", []):
                archive_path = archive["archive_path"]
                archive_bname = os.path.splitext(
                    os.path.basename(archive_path)
                )[0]
                pipeline._last_run_dirs.add(os.path.dirname(archive_path))
                break

        try:
            image = cv2.imread(image_path)
            if image is None:
                logger.warning(
                    "[SBIANCHETTA] Impossibile caricare %s", image_path,
                )
                continue
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            main_page.progress_update.emit(
                index, total_images, 1, 10, False,
            )

            blk_list, _ = get_blk_list(
                pipeline, image, image_path, source_lang,
                skip_detection, existing_blk_list,
            )
            if not blk_list:
                continue
            main_page.progress_update.emit(
                index, total_images, 2, 10, False,
            )

            # Popola i blocchi con spazi (al posto di OCR e traduzione)
            for blk in blk_list:
                blk.text = " "
                blk.translation = " "
            main_page.progress_update.emit(
                index, total_images, 3, 10, False,
            )

            ensure_inpainter(pipeline, settings_page)
            inpaint_input_img = inpaint(
                pipeline, image, blk_list, settings_page,
            )
            inpaint_input_img_rgb = cv2.cvtColor(
                inpaint_input_img, cv2.COLOR_BGR2RGB,
            )

            main_page.image_history[image_path] = [image_path]
            main_page.current_history_index[image_path] = 0
            main_page.image_processed.emit(
                index, inpaint_input_img, image_path,
            )
            main_page.progress_update.emit(
                index, total_images, 5, 10, False,
            )

            export_settings = settings_page.get_export_settings()
            if export_settings.get("export_inpainted_image", False):
                cleaned_dir = os.path.join(
                    directory, f"comic_translate_{timestamp}",
                    "cleaned_images", archive_bname,
                )
                os.makedirs(cleaned_dir, exist_ok=True)
                cv2.imwrite(
                    os.path.join(
                        cleaned_dir, f"{base_name}_cleaned{extension}"
                    ),
                    inpaint_input_img_rgb,
                )

            trg_lng_cd = main_page.lang_mapping.get(
                target_lang, target_lang,
            )
            text_items_state = render_text_items(
                blk_list, image, inpaint_input_img_rgb,
                main_page, trg_lng_cd,
            )

            save_translated(
                pipeline, inpaint_input_img_rgb, blk_list,
                text_items_state, image_path, archive_bname,
                timestamp, directory, base_name, extension,
                export_settings,
            )

            if index == main_page.curr_img_idx:
                main_page.blk_list = blk_list

            main_page.progress_update.emit(
                index, total_images, 10, 10, False,
            )
        except Exception as exc:
            log_encoding_error(
                text=f"Errore sbianchetta per {image_path}: {exc}",
                encoding="utf-8",
                error=exc,
                operation="sbianchetta",
            )
            logger.exception(
                "[SBIANCHETTA] Errore durante elaborazione %s",
                image_path,
            )
            continue

    _repack_archives(main_page, timestamp, total_images)

    log_batch_operation(
        "sbianchetta_completed",
        total_images,
        total_images,
        0,
        time.time() - start_time,
    )
    main_page.progress_update.emit(total_images, total_images, 10, 10, False)
    pipeline._cleanup_stray_translated_files()
    pipeline._cleanup_after_batch()
    return True