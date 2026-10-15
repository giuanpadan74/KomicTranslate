import msgpack
import cv2
import os
import tempfile
import zipfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from .parsers import ProjectEncoder, ProjectDecoder, ensure_string_keys
from .ctpr_compat import join_ctpr_files_v4

def save_state_to_proj_file(comic_translate, file_name):
    """
    Saves the state of the comic_translate object to a JSON file and a folder of images.
    """
    import json
    
    # Create a temporary directory for images
    with tempfile.TemporaryDirectory() as temp_dir:
        images_dir = os.path.join(temp_dir, "images")  # Cambiato da "unique_images"
        os.makedirs(images_dir, exist_ok=True)

        # Helper function to serialize objects
        def serialize_objects(obj_dict):
            result = {}
            for k, v in obj_dict.items():
                if hasattr(v, 'to_dict') and callable(getattr(v, 'to_dict')):
                    try:
                        result[k] = v.to_dict()
                    except RuntimeError as e:
                        if "Internal C++ object" in str(e) and "already deleted" in str(e):
                            print(f"Warning: Skipping deleted C++ object {k}: {str(e)}")
                            # Skip deleted C++ objects completely
                            continue
                        else:
                            print(f"Warning: Error serializing {k}: {str(e)}")
                            try:
                                result[k] = str(v)  # Fallback to string
                            except RuntimeError:
                                print(f"Warning: Skipping completely inaccessible object {k}")
                                continue
                    except Exception as e:
                        print(f"Warning: Error serializing {k}: {str(e)}")
                        try:
                            result[k] = str(v)  # Fallback to string
                        except Exception:
                            print(f"Warning: Skipping completely inaccessible object {k}")
                            continue
                elif isinstance(v, dict):
                    result[k] = serialize_objects(v)  # Recursively handle nested dicts
                else:
                    result[k] = v
            return result

        # Initialize the state dictionary with serialized objects
        state = {
            'current_image_index': comic_translate.curr_img_idx,
            'image_states': comic_translate.image_states,
            'unique_images': {},  # Will store id to file_name mapping
            'image_data_references': {},
            'image_files_references': {},
            'in_memory_history_references': {},
            'image_history_references': {},
            'original_image_files': comic_translate.image_files,
            'current_history_index': comic_translate.current_history_index,
            'displayed_images': list(comic_translate.displayed_images),
            'loaded_images': comic_translate.loaded_images,
            'text_blocks': serialize_objects(getattr(comic_translate, 'text_blocks', {})),
            'rect_items': serialize_objects(getattr(comic_translate, 'rect_items', {})),
            'text_items': serialize_objects(getattr(comic_translate, 'text_items', {}))
        }

        image_id_counter = 0
        image_path_to_id = {}
        unique_images = {}

        # Helper function to copy image and assign ID
        def copy_and_assign(file_path):
            nonlocal image_id_counter
            if file_path not in image_path_to_id:
                image_id = image_id_counter
                image_id_counter += 1
                image_path_to_id[file_path] = image_id
                
                bname = os.path.basename(file_path)
                # unique_images_dir non era definito in questa funzione (lo era
                # solo nel loader): NameError al primo salvataggio. La cartella
                # di destinazione e' la stessa usata dal loader.
                new_file_path = os.path.join(images_dir, bname)
                
                # Copy file from disk
                shutil.copy2(file_path, new_file_path)
                unique_images[image_id] = bname
            
            return image_path_to_id[file_path]

        # Process in_memory_history
        for file, history in comic_translate.in_memory_history.items():
            state['in_memory_history_references'][file] = []
            for idx, img in enumerate(history):
                path = comic_translate.image_history[file][idx]
                if idx == comic_translate.current_history_index.get(file, 0):
                    # Link to image_data
                    image_id = copy_and_assign(path)
                    state['image_data_references'][file] = image_id
                else:
                    image_id = copy_and_assign(path)
                state['in_memory_history_references'][file].append(image_id)

        # Process image_files and image_history
        for file_path in comic_translate.image_files:
            if file_path in comic_translate.image_history:
                state['image_history_references'][file_path] = []
                history_paths = comic_translate.image_history[file_path]
                for path in history_paths:
                    image_id = copy_and_assign(path)
                    state['image_history_references'][file_path].append(image_id)
            else:
                # This file hasn't been loaded before
                image_id = copy_and_assign(file_path)
                state['image_files_references'][file_path] = image_id

        state['unique_images'] = ensure_string_keys(unique_images)

        # Serialize the state to JSON instead of msgpack
        json_file = os.path.join(temp_dir, "project_data.json")  # Cambiato da "state.msgpack"
        
        with open(json_file, 'w', encoding='utf-8') as file:
            json.dump(state, file, indent=2, ensure_ascii=False, default=str)
        
        # Create a zip file containing the JSON file and images folder
        with zipfile.ZipFile(file_name, 'w', zipfile.ZIP_STORED) as zipf:
            zipf.write(json_file, arcname="project_data.json")
            for root, _, files in os.walk(images_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname=arcname)

def load_state_from_proj_file(comic_translate, file_name):
    import json
    
    if not hasattr(comic_translate, 'temp_dir'):
        comic_translate.temp_dir = tempfile.mkdtemp()
    
    temp_dir = comic_translate.temp_dir
    
    if file_name.lower().endswith('.ctpr'):
        # Extract the .ctpr file to a temporary directory
        with zipfile.ZipFile(file_name, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
    
    json_file = os.path.join(temp_dir, "project_data.json")  # Cambiato da "state.msgpack"
    images_dir = os.path.join(temp_dir, "images")  # Cambiato da "unique_images"
    
    # Load the state from the JSON file
    with open(json_file, 'r', encoding='utf-8') as file:
        state = json.load(file)
    
    decoder = ProjectDecoder()

    # Use local references to attributes for faster access
    image_data = comic_translate.image_data
    temp_dir = comic_translate.temp_dir
    in_memory_history = comic_translate.in_memory_history
    image_history = comic_translate.image_history
    original_to_temp = {}

    image_states = {}
    current_history_index = {}
    displayed_images = set()
    loaded_images = []

    if file_name.lower().endswith('.ctpr'):
        # Extract the .ctpr file to a temporary directory
        with zipfile.ZipFile(file_name, 'r') as zip_ref:
            zip_ref.extractall(comic_translate.temp_dir)

    # temp_dir/unique_images_dir non erano definiti in questa funzione (erano
    # locali di save_state_to_proj_file) => NameError immediato. Uso la
    # cartella dell'oggetto e la stessa sotto-cartella "images" del saver.
    temp_dir = comic_translate.temp_dir
    unique_images_dir = os.path.join(temp_dir, "images")

    msgpack_file = os.path.join(temp_dir, "state.msgpack")

    if not os.path.exists(msgpack_file):
        raise FileNotFoundError(
            f"state.msgpack non trovato in '{temp_dir}'. "
            "Il formato .ctpr prodotto da questo loader non e' piu' quello "
            "attualmente generato: usare app.controllers.project_controller "
            "(save_project_new / _load_pages_project)."
        )

    # Load the state from the msgpack file
    with open(msgpack_file, 'rb') as file:
        unpacker = msgpack.Unpacker(file, object_hook=decoder.decode, strict_map_key=True)
        try:
            map_size = unpacker.read_map_header()
            
            state = {}
            for _ in range(map_size):
                key = unpacker.unpack()
                value = unpacker.unpack()
                state[key] = value
        except Exception as e:
            print(f"[ERROR] Error during deserialization: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    # Update comic_translate with the loaded state
    for key, value in state.items():
        if hasattr(comic_translate, key):
            print(f"[DEBUG] Caricando attributo: {key}, tipo: {type(value)}")
            if key == 'blk_list':
                print(f"[DEBUG] blk_list contiene {len(value)} elementi")
                for i, blk in enumerate(value[:3]):  # Mostra primi 3 per debug
                    print(f"[DEBUG] Block {i}: pos=({blk.xyxy[0] if blk.xyxy is not None else 'None'}, {blk.xyxy[1] if blk.xyxy is not None else 'None'}), text='{blk.text[:20]}...'")
            setattr(comic_translate, key, value)
    
    # Verifica finale
    print(f"[DEBUG] Dopo caricamento, blk_list ha {len(comic_translate.blk_list)} elementi")

    # Process image states and history
    if 'image_states' in state:
        comic_translate.image_states = state['image_states']

    if 'current_history_index' in state:
        comic_translate.current_history_index = state['current_history_index']

    # Build img_id_to_usage mapping
    img_id_to_usage = {}

    # Helper function to process references
    def process_references(ref_dict, ref_type):
        for file_path, img_id_str in ref_dict.items():
            img_id = int(img_id_str)
            if ref_type in ['in_memory_history', 'image_history']:
                for idx, img_id_sub_str in enumerate(img_id_str):
                    img_id_sub = int(img_id_sub_str)
                    img_id_to_usage.setdefault(img_id_sub, []).append((ref_type, file_path, idx))
            else:
                img_id_to_usage.setdefault(img_id, []).append((ref_type, file_path))

    # Process different references
    process_references(state.get('image_data_references', {}), 'image_data')
    process_references(state.get('image_files_references', {}), 'image_files')

    # For in_memory_history_references and image_history_references
    for ref_type in ['in_memory_history_references', 'image_history_references']:
        for file_path, img_id_list in state.get(ref_type, {}).items():
            for idx, img_id_str in enumerate(img_id_list):
                img_id = int(img_id_str)
                usage_type = 'in_memory_history' if ref_type == 'in_memory_history_references' else 'image_history'
                img_id_to_usage.setdefault(img_id, []).append((usage_type, file_path, idx))

    unique_images = state.get('unique_images', {})

    # Helper function to process a single image
    def process_image(img_file_name, usages, image_data,
                     original_to_temp, in_memory_history, image_history):
        img_path = os.path.join(unique_images_dir, img_file_name)

        for usage in usages:
            usage_type = usage[0]
            if usage_type == 'image_data':
                file_path = usage[1]
                img = cv2.imread(img_path)
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                image_data[file_path] = img
            elif usage_type == 'in_memory_history':
                img = cv2.imread(img_path)
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                file_path, idx = usage[1], usage[2]
                in_memory_history.setdefault(file_path, [])
                history = in_memory_history[file_path]
                while len(history) <= idx:
                    history.append(None)
                history[idx] = img
            elif usage_type == 'image_files':
                file_path = usage[1]
                temp_path = img_path
                original_to_temp[file_path] = temp_path
            elif usage_type == 'image_history':
                file_path, idx = usage[1], usage[2]
                image_history.setdefault(file_path, [])
                history = image_history[file_path]
                while len(history) <= idx:
                    history.append(None)
                history[idx] = img_path

    # Process images in parallel
    with ThreadPoolExecutor() as executor:
        future_to_img_id = {
            executor.submit(process_image, img_file_name, img_id_to_usage[int(img_id)],
                            image_data, original_to_temp,
                            in_memory_history, image_history): img_id
            for img_id, img_file_name in unique_images.items() if int(img_id) in img_id_to_usage
        }

        for future in as_completed(future_to_img_id):
            img_id = future_to_img_id[future]
            try:
                future.result()
            except Exception as exc:
                print(f'Image ID {img_id} generated an exception: {exc}')

    # Finalize loading by updating comic_translate attributes
    comic_translate.curr_img_idx = state.get('current_image_index', 0)

    original_image_files = state.get('original_image_files', [])
    comic_translate.image_files = [
        original_to_temp.get(file, file) for file in original_image_files
    ]

    image_states = state.get('image_states', {})
    comic_translate.image_states = {
        original_to_temp.get(file, file): img_state for file, img_state in image_states.items()
    }

    # Carica i text_blocks se presenti
    if 'text_blocks' in state:
        comic_translate.text_blocks = state['text_blocks']
    
    # Carica i rect_items se presenti
    if 'rect_items' in state:
        comic_translate.rect_items = state['rect_items']
    
    # Carica i text_items se presenti
    if 'text_items' in state:
        comic_translate.text_items = state['text_items']

    current_history_index = state.get('current_history_index', {})
    comic_translate.current_history_index = {
        original_to_temp.get(file, file): index for file, index in current_history_index.items()
    }

    displayed_images = state.get('displayed_images', [])
    comic_translate.displayed_images = set(
        original_to_temp.get(i, i) for i in displayed_images
    )
    loaded_images = state.get('loaded_images', [])
    comic_translate.loaded_images = [
        original_to_temp.get(file, file) for file in loaded_images
    ]

    comic_translate.image_data = {
        original_to_temp.get(file, file): img 
        for file, img in image_data.items()
    }

    comic_translate.in_memory_history = {
        original_to_temp.get(file, file): imgs 
        for file, imgs in in_memory_history.items()
    }

    comic_translate.image_history = {
        original_to_temp.get(file_path, file_path): history_list
        for file_path, history_list in image_history.items()
    }

def join_ctpr_files(ctpr_files, output_file, file_mappings=None):
    return join_ctpr_files_v4(ctpr_files, output_file, file_mappings)
