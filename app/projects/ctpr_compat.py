import copy
import glob
import json
import os
import shutil
import tempfile
import zipfile


def adapt_project_data_to_pages(temp_dir, project_data):
    if project_data.get("save_type") == "pages" or "pages" in project_data:
        return project_data

    def relpath(path):
        return os.path.relpath(path, temp_dir).replace("\\", "/")

    pages = []
    save_type = project_data.get("save_type", "single")
    source_lang = project_data.get("source_lang", "")
    target_lang = project_data.get("target_lang", "")
    current_index = int(project_data.get("current_image_index", 0))
    manifest = sorted(
        project_data.get("image_manifest", []),
        key=lambda entry: int(entry.get("index", 0)),
    )

    if save_type == "all_images":
        if manifest:
            image_entries = manifest
        else:
            image_entries = []
            image_paths = glob.glob(os.path.join(temp_dir, "images", "*", "*.*"))
            for idx, image_path in enumerate(sorted(image_paths)):
                image_entries.append(
                    {
                        "index": idx,
                        "source_name": os.path.basename(image_path),
                        "display_relpath": relpath(image_path),
                        "original_relpath": None,
                    }
                )

        all_text_blocks = project_data.get("all_text_blocks", {})
        all_text_items = project_data.get("all_text_items", {})
        for entry in image_entries:
            index = int(entry.get("index", len(pages)))
            pages.append(
                {
                    "page_id": f"page_{index:03d}",
                    "index": index,
                    "source_name": entry.get("source_name", f"page_{index:03d}.jpg"),
                    "image": {
                        "display_relpath": entry.get("display_relpath"),
                        "original_relpath": entry.get("original_relpath"),
                    },
                    "viewer_state": {"overlays_hidden": True, "rectangles": [], "text_items_state": []},
                    "brush_strokes": [],
                    "text_blocks": all_text_blocks.get(str(index), []),
                    "text_items": all_text_items.get(str(index), []),
                    "svg_items": [],
                }
            )
    else:
        image_candidates = sorted(glob.glob(os.path.join(temp_dir, "images", "*.*")))
        if not image_candidates:
            image_candidates = sorted(glob.glob(os.path.join(temp_dir, "images", "*", "*.*")))
        if image_candidates:
            display_path = image_candidates[0]
            source_name = os.path.basename(display_path)
            original_path = os.path.join(temp_dir, "originals", source_name)
            pages.append(
                {
                    "page_id": "page_000",
                    "index": 0,
                    "source_name": source_name,
                    "image": {
                        "display_relpath": relpath(display_path),
                        "original_relpath": relpath(original_path) if os.path.exists(original_path) else None,
                    },
                    "viewer_state": {"overlays_hidden": True, "rectangles": [], "text_items_state": []},
                    "brush_strokes": [],
                    "text_blocks": project_data.get("text_blocks", []),
                    "text_items": project_data.get("text_items", []),
                    "svg_items": [],
                }
            )

    adapted = {
        "version": "4.0",
        "created_with": project_data.get("created_with", "KomicTranslate"),
        "save_type": "pages",
        "pages": pages,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "current_image_index": current_index,
        "total_images": len(pages),
    }
    print(f"[CTPR_COMPAT] Adattato progetto legacy a schema pages con {len(pages)} pagine")
    return adapted


def join_ctpr_files_v4(ctpr_files, output_file, file_mappings=None):
    with tempfile.TemporaryDirectory() as temp_dir:
        images_dir = os.path.join(temp_dir, "images")
        originals_dir = os.path.join(temp_dir, "originals")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(originals_dir, exist_ok=True)

        combined_pages = []
        source_lang = ""
        target_lang = ""

        for page_index, ctpr_file in enumerate(ctpr_files):
            extract_dir = os.path.join(temp_dir, f"src_{page_index:03d}")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(ctpr_file, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

            project_path = os.path.join(extract_dir, "project_data.json")
            with open(project_path, "r", encoding="utf-8") as handle:
                project_data = adapt_project_data_to_pages(extract_dir, json.load(handle))

            if not source_lang:
                source_lang = project_data.get("source_lang", "")
                target_lang = project_data.get("target_lang", "")

            for page in project_data.get("pages", []):
                page_copy = copy.deepcopy(page)
                source_name = page_copy.get("source_name") or os.path.basename(
                    page_copy["image"]["display_relpath"]
                )
                mapped_name = file_mappings.get(source_name, source_name) if file_mappings else source_name
                image_subdir = os.path.join(images_dir, f"{len(combined_pages):03d}")
                original_subdir = os.path.join(originals_dir, f"{len(combined_pages):03d}")
                os.makedirs(image_subdir, exist_ok=True)
                os.makedirs(original_subdir, exist_ok=True)

                display_src = os.path.join(extract_dir, page_copy["image"]["display_relpath"])
                display_dst = os.path.join(image_subdir, mapped_name)
                shutil.copy2(display_src, display_dst)

                original_relpath = page_copy["image"].get("original_relpath")
                copied_original_relpath = None
                if original_relpath:
                    original_src = os.path.join(extract_dir, original_relpath)
                    if os.path.exists(original_src):
                        original_dst = os.path.join(original_subdir, mapped_name)
                        shutil.copy2(original_src, original_dst)
                        copied_original_relpath = os.path.relpath(original_dst, temp_dir).replace("\\", "/")

                page_copy["index"] = len(combined_pages)
                page_copy["page_id"] = f"page_{len(combined_pages):03d}"
                page_copy["source_name"] = mapped_name
                page_copy["image"] = {
                    "display_relpath": os.path.relpath(display_dst, temp_dir).replace("\\", "/"),
                    "original_relpath": copied_original_relpath,
                }
                combined_pages.append(page_copy)

        project_data = {
            "version": "4.0",
            "created_with": "KomicTranslate",
            "save_type": "pages",
            "pages": combined_pages,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "current_image_index": 0,
            "total_images": len(combined_pages),
        }

        project_path = os.path.join(temp_dir, "project_data.json")
        with open(project_path, "w", encoding="utf-8") as handle:
            json.dump(project_data, handle, indent=2, ensure_ascii=False)

        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(project_path, "project_data.json")
            for base_dir in (images_dir, originals_dir):
                for root, _, files in os.walk(base_dir):
                    for file_name in files:
                        file_path = os.path.join(root, file_name)
                        zipf.write(file_path, os.path.relpath(file_path, temp_dir))
        return True
