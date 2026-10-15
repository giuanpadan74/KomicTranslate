import msgpack
import numpy as np
import datetime
from datetime import datetime, date
from PySide6 import QtGui
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor  # usato direttamente in decode_outline_info
from modules.utils.textblock import TextBlock
from ..ui.canvas.text_item import OutlineInfo, OutlineType, TextBlockItem as CanvasTextBlock
from ..ui.canvas.rectangle import MoveableRectItem

class ProjectDecoder:
    """Classe per la deserializzazione di oggetti da formati di salvataggio"""
    
    def __init__(self):
        self.decoders = {
            'ndarray': self.decode_numpy_array,
            'TextBlock': self.decode_text_block,
            'QColor': self.decode_qcolor,
            'QPainterPath': self.decode_qpainterpath,
            'OutlineInfo': self.decode_outline_info,
            'tuple': self.decode_tuple,
            'Qt.Alignment': self.decode_alignment,
            'Qt.LayoutDirection': self.decode_layout_direction,
            'MoveableRectItem': self.decode_movable_rect_item,
            'TextBlockItem': self.decode_text_block_item,
            'datetime': self.decode_datetime,
            'date': self.decode_date
        }
    
    def decode(self, obj):
        """Metodo principale di decodifica"""
        if isinstance(obj, dict):
            if '__class__' in obj:
                class_name = obj['__class__']
                if class_name in self.decoders:
                    return self.decoders[class_name](obj)
                else:
                    print(f"Warning: Unknown class {class_name}")
                    return {k: self.decode(v) for k, v in obj.items() if not k.startswith('__')}
            return {k: self.decode(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.decode(x) for x in obj]
        else:
            return obj
    
    def decode_numpy_array(self, obj):
        """Decodifica un array NumPy"""
        try:
            if '__ndarray__' in obj:
                return np.array(obj['__ndarray__'], dtype=obj.get('dtype', 'float64'))
            elif 'data' in obj:  # Vecchio formato
                data = obj['data']
                dtype = np.dtype(obj.get('dtype', 'float64'))
                if 'shape' in obj:
                    return np.frombuffer(data, dtype=dtype).reshape(obj['shape'])
                return np.frombuffer(data, dtype=dtype)
            return np.array([])
        except Exception as e:
            print(f"Error decoding numpy array: {e}")
            return np.array([])
    
    def decode_text_block(self, obj):
        """Decodifica un TextBlock"""
        from modules.utils.textblock import TextBlock
        if hasattr(TextBlock, 'from_dict'):
            return TextBlock.from_dict(obj)
        return obj
    
    def decode_qcolor(self, obj):
        """Decodifica un QColor.

        Accetta sia lo schema 'red/green/blue/alpha' (usato da
        ProjectEncoder.encode_qcolor) sia 'r/g/b/a' (lo schema prodotto
        dalla versione @staticmethod di encode_qcolor). Senza questa
        compatibilita' ogni colore salvato veniva riletto come nero opaco.
        """
        from PySide6 import QtGui
        return QtGui.QColor(
            obj.get('red', obj.get('r', 0)),
            obj.get('green', obj.get('g', 0)),
            obj.get('blue', obj.get('b', 0)),
            obj.get('alpha', obj.get('a', 255))
        )
    
    def decode_qpainterpath(self, obj):
        """Decodifica un QPainterPath"""
        from PySide6 import QtGui, QtCore
        path = QtGui.QPainterPath()
        for element in obj.get('elements', []):
            point = QtCore.QPointF(element['x'], element['y'])
            if element['type'] == 0:  # MoveTo
                path.moveTo(point)
            elif element['type'] == 1:  # LineTo
                path.lineTo(point)
            # Aggiungi qui altri tipi di elemento se necessario
        return path
    
    def decode_outline_info(self, obj):
        """Decodifica un OutlineInfo"""
        from ..ui.canvas.text_item import OutlineInfo, OutlineType
        from PySide6 import QtGui
        
        color = self.decode_qcolor(obj['color']) if obj.get('color') else None
        outline_type = getattr(OutlineType, obj.get('type', 'NO_LINE'), OutlineType.NO_LINE)
        
        outline = OutlineInfo()
        outline.width = obj.get('width', 1.0)
        outline.color = color
        if hasattr(outline, 'type'):
            outline.type = outline_type
            
        return outline
    
    def decode_tuple(self, obj):
        """Decodifica una tupla"""
        return tuple(obj.get('data', []))
    
    def decode_alignment(self, obj):
        """Decodifica un allineamento Qt"""
        from PySide6 import QtCore
        return QtCore.Qt.AlignmentFlag(obj.get('value', 0))
    
    def decode_layout_direction(self, obj):
        """Decodifica una direzione di layout Qt"""
        from PySide6 import QtCore
        return QtCore.Qt.LayoutDirection(obj.get('value', 0))
    
    def decode_movable_rect_item(self, obj):
        """Decodifica un MoveableRectItem"""
        from ..ui.canvas.rectangle import MoveableRectItem
        return MoveableRectItem.from_dict(obj)
    
    def decode_text_block_item(self, obj):
        """Decodifica un TextBlockItem"""
        from ..ui.canvas.text_item import TextBlockItem
        return TextBlockItem.from_dict(obj)
    
    def decode_datetime(self, obj):
        """Decodifica un datetime"""
        from datetime import datetime
        return datetime.fromisoformat(obj.get('__datetime__'))
    
    def decode_date(self, obj):
        """Decodifica una data"""
        from datetime import date
        return date.fromisoformat(obj.get('__date__'))


class ProjectEncoder:
    def __init__(self):
        self.encoders = [
            (np.ndarray, self.encode_numpy_array),
            (CanvasTextBlock, self.encode_text_block),
            (QtGui.QColor, self.encode_qcolor),
            (QtGui.QPainterPath, self.encode_qpainterpath),
            (OutlineInfo, self.encode_outline_info),
            (tuple, self.encode_tuple),
            (Qt.AlignmentFlag, self.encode_alignment),
            (Qt.Alignment, self.encode_alignment),
            (Qt.LayoutDirection, self.encode_layout_direction),
            (MoveableRectItem, self.encode_movable_rect_item),
        ]

    def encode_numpy_array(self, obj):
        """Codifica un array NumPy in un formato serializzabile"""
        return {
            '__ndarray__': obj.tolist(),
            'dtype': str(obj.dtype),
            'shape': obj.shape,
            '__class__': 'ndarray'
        }
        
    def encode_text_block(self, obj):
        """Codifica un oggetto TextBlock"""
        if hasattr(obj, 'to_dict'):
            result = obj.to_dict()
            result['__class__'] = 'TextBlock'
            return result
        return str(obj)
        
    def encode_qcolor(self, obj):
        """Codifica un oggetto QColor"""
        return {
            'red': obj.red(),
            'green': obj.green(),
            'blue': obj.blue(),
            'alpha': obj.alpha(),
            '__class__': 'QColor'
        }
        
    def encode_qpainterpath(self, obj):
        """Codifica un oggetto QPainterPath"""
        elements = []
        for i in range(obj.elementCount()):
            element = obj.elementAt(i)
            elements.append({
                'type': element.type,
                'x': element.x,
                'y': element.y
            })
        return {
            'elements': elements,
            '__class__': 'QPainterPath'
        }
        
    def encode_outline_info(self, obj):
        """Codifica un oggetto OutlineInfo"""
        return {
            'width': obj.width,
            'color': self.encode_qcolor(obj.color) if obj.color else None,
            'type': obj.type.name if hasattr(obj, 'type') else 'NO_LINE',
            '__class__': 'OutlineInfo'
        }
        
    def encode_tuple(self, obj):
        """Codifica una tupla"""
        return {
            'data': list(obj),
            '__class__': 'tuple'
        }
        
    def encode_alignment(self, obj):
        """Codifica un allineamento Qt"""
        return {
            'value': int(obj),
            '__class__': 'Qt.Alignment'
        }
        
    def encode_layout_direction(self, obj):
        """Codifica una direzione di layout Qt"""
        return {
            'value': int(obj),
            '__class__': 'Qt.LayoutDirection'
        }
        
    def encode_movable_rect_item(self, obj):
        """Codifica un oggetto MoveableRectItem"""
        if hasattr(obj, 'to_dict'):
            result = obj.to_dict()
            result['__class__'] = 'MoveableRectItem'
            return result
        return str(obj)
    
    def encode(self, obj):
        """Metodo principale di codifica che gestisce tutti i tipi"""
        try:
            # Controlla se esiste un encoder specifico per questo tipo
            for type_, encoder in self.encoders:
                if isinstance(obj, type_):
                    return encoder(obj)
            
            # Gestione esplicita di datetime e date
            import datetime
            from PySide6 import QtCore, QtGui
            
            # Gestione oggetti datetime/date
            if hasattr(obj, 'isoformat') and hasattr(obj, 'year') and hasattr(obj, 'month') and hasattr(obj, 'day'):
                if hasattr(obj, 'hour') and hasattr(obj, 'minute') and hasattr(obj, 'second'):
                    # È un datetime
                    return {'__datetime__': obj.isoformat(), '__class__': 'datetime'}
                else:
                    # È solo una data
                    return {'__date__': obj.isoformat(), '__class__': 'date'}
            
            # Gestione QColor
            if isinstance(obj, QtGui.QColor):
                return {
                    '__qcolor__': {
                        'red': obj.red(),
                        'green': obj.green(),
                        'blue': obj.blue(),
                        'alpha': obj.alpha()
                    },
                    '__class__': 'QColor'
                }
                
            # Gestione EnumType (es. Qt enums)
            if isinstance(obj, (QtCore.Qt.AlignmentFlag, QtCore.Qt.LayoutDirection)):
                return {
                    '__enum__': {
                        'type': type(obj).__name__,
                        'value': int(obj)
                    },
                    '__class__': 'EnumType'
                }
                
            # Gestione TextBlock
            if hasattr(obj, 'to_dict') and hasattr(obj, 'from_dict'):
                result = obj.to_dict()
                result['__class__'] = obj.__class__.__name__
                return result
                
            if isinstance(obj, np.ndarray):
                return {'__ndarray__': obj.tolist(), 'dtype': str(obj.dtype)}
            elif isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
                                np.int16, np.int32, np.int64, np.uint8,
                                np.uint16, np.uint32, np.uint64)):
                return int(obj)
            elif isinstance(obj, (np.float_, np.float16, np.float32,
                                np.float64)):
                return float(obj)
            elif isinstance(obj, (np.complex_, np.complex64, np.complex128)):
                return {'__complex__': True, 'real': obj.real, 'imag': obj.imag}
            elif isinstance(obj, (np.bool_)):
                return bool(obj)
            elif isinstance(obj, (np.void)):
                return None
            elif isinstance(obj, (np.str_, str)):
                return str(obj)
            elif isinstance(obj, (np.bytes_, bytes)):
                return {'__bytes__': True, 'data': obj.decode('latin1')}
            elif isinstance(obj, (np.datetime64,)):
                return {'__datetime64__': True, 'data': str(obj)}
            elif isinstance(obj, (np.timedelta64,)):
                return {'__timedelta64__': True, 'data': str(obj)}
            elif isinstance(obj, (np.generic,)):
                return obj.item()
            elif isinstance(obj, (complex, np.complex_)):
                return {'__complex__': True, 'real': obj.real, 'imag': obj.imag}
            elif isinstance(obj, set):
                return {'__set__': list(obj)}
            elif isinstance(obj, (datetime.date, datetime.datetime)):
                return {'__datetime__': obj.isoformat()}
            elif hasattr(obj, 'to_dict') and callable(obj.to_dict):
                try:
                    result = obj.to_dict()
                    if not isinstance(result, dict):
                        raise ValueError(f"to_dict() did not return a dictionary for {type(obj)}")
                    result['__class__'] = obj.__class__.__name__
                    return result
                except Exception as e:
                    print(f"Error encoding {type(obj)}: {str(e)}")
                    return {'__error__': f"Failed to serialize {type(obj).__name__}: {str(e)}"}
            elif isinstance(obj, dict):
                return {str(k): self.encode(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [self.encode(x) for x in obj]
            else:
                # Try to convert to a primitive type
                try:
                    if hasattr(obj, '__dict__'):
                        return {'__class__': obj.__class__.__name__, 
                               '__dict__': self.encode(obj.__dict__)}
                    return str(obj)
                except:
                    return str(obj)
        except Exception as e:
            print(f"Error in ProjectEncoder: {str(e)}")
            return {'__error__': f"Failed to serialize: {str(e)}"}

    @staticmethod
    def encode_numpy_scalar(obj):
        return obj.item()

    @staticmethod
    def encode_tuple(obj):
        return {
            'type': 'tuple',
            'data': list(obj)
        }

    @staticmethod
    def encode_numpy_array(obj):
        if obj.ndim == 0:  # scalar numpy array
            return {
                'type': 'numpy.scalar',
                'data': obj.item(),
                'dtype': str(obj.dtype)
            }
        return {
            'type': 'numpy.ndarray',
            'data': obj.tobytes(),
            'shape': obj.shape,
            'dtype': str(obj.dtype)
        }

    @staticmethod
    def encode_text_block(obj):
        return {
            '__class__': 'TextBlock',
            'text': obj.text,
            'rect': obj.rect,
            'angle': obj.angle,
            'font_family': obj.font_family,
            'font_size': obj.font_size,
            'color': ProjectEncoder.encode_qcolor(obj.color),
            'alignment': obj.alignment,
            'translation': obj.translation
        }

    @staticmethod
    def encode_qcolor(obj):
        return {
            '__class__': 'QColor',
            'r': obj.red(),
            'g': obj.green(),
            'b': obj.blue(),
            'a': obj.alpha()
        }

    @staticmethod
    def encode_qpainterpath(obj):
        elements = []
        for i in range(obj.elementCount()):
            element = obj.elementAt(i)
            elements.append({
                'type': element.type,
                'x': element.x,
                'y': element.y
            })
        return {
            '__class__': 'QPainterPath',
            'elements': elements
        }

    @staticmethod
    def encode_alignment_flag(obj):
        return {
            'type': 'alignmentflag',
            'data': obj.value
        }

    @staticmethod
    def encode_outline_info(obj):
        return {
            'type': 'selection_outline_info',
            'data': {
                'start': obj.start,
                'end': obj.end,
                'color': ProjectEncoder.encode_qcolor(obj.color),
                'width': obj.width,
                'type': obj.type.value
            }
        }

    @staticmethod
    def encode_layout_flag(obj):
        return {
            'type': 'layoutflag',
            'data': obj.value
        }

    @staticmethod
    def encode_alignment(obj):
        return {
            'type': 'alignment',
            'data': obj.value
        }

    @staticmethod
    def encode_layout_direction(obj):
        return {
            'type': 'layoutdirection',
            'data': obj.value
        }
        
    @staticmethod
    def encode_movable_rect_item(obj):
        """Codifica un oggetto MoveableRectItem in un dizionario"""
        return obj.to_dict()


# Rimossa la seconda definizione di ProjectDecoder
# La prima implementazione (righe 10-139) contiene già tutti i metodi necessari
        
    def register_class(self, class_name, class_type):
        self.class_registry[class_name] = class_type

    def decode(self, obj):
        if not isinstance(obj, dict):
            return obj

        for is_type, decoder in self.decoders:
            if is_type(obj):
                return decoder(obj)
        return obj
        
    def is_custom_class(self, obj):
        return '__class__' in obj and ('__dict__' in obj or any(k not in ['__class__', '__error__'] for k in obj.keys()))
        
    def decode_custom_class(self, obj):
        """Decode a custom class from a dictionary"""
        class_name = obj.get('__class__')
        
        # Handle error case
        if '__error__' in obj:
            print(f"Warning: Could not deserialize {class_name}: {obj['__error__']}")
            return None
            
        # Try to find the class in registered classes or import it
        if class_name in self.class_registry:
            cls = self.class_registry[class_name]
        else:
            try:
                # Try to import the class dynamically
                if class_name == 'TextBlockItem':
                    from app.ui.canvas.text_item import TextBlockItem
                    cls = TextBlockItem
                    self.register_class('TextBlockItem', TextBlockItem)
                elif class_name == 'MoveableRectItem':
                    from app.ui.canvas.rectangle import MoveableRectItem
                    cls = MoveableRectItem
                    self.register_class('MoveableRectItem', MoveableRectItem)
                # RectangleItem rimosso - ora si utilizzano solo SVG
                else:
                    print(f"[WARNING] Unknown class {class_name}")
                return obj
            except Exception as e:
                print(f"[ERROR] Error importing class {class_name}: {str(e)}")
                import traceback
                traceback.print_exc()
                return obj
        
        # Try to use from_dict if available
        if hasattr(cls, 'from_dict') and callable(getattr(cls, 'from_dict')):
            try:
                # Remove class marker before passing to from_dict
                data = {k: v for k, v in obj.items() if k != '__class__'}
                return cls.from_dict(data)
            except Exception as e:
                print(f"[ERROR] Error calling from_dict on {class_name}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Fall back to direct attribute setting
        if hasattr(cls, '__dict__'):
            try:
                instance = cls()
                if '__dict__' in obj:
                    for k, v in obj['__dict__'].items():
                        setattr(instance, k, self.decode(v))
                return instance
            except Exception as e:
                print(f"Error creating instance of {class_name}: {str(e)}")
        
        return obj

    @staticmethod
    def decode_text_block(obj):
        text_block = CanvasTextBlock()
        text_block.text = obj.get('text', '')
        text_block.rect = obj.get('rect', QtGui.QRectF())
        text_block.angle = obj.get('angle', 0)
        text_block.font_family = obj.get('font_family', 'Arial')
        text_block.color = ProjectDecoder.decode_qcolor(obj.get('color'))
        text_block.alignment = obj.get('alignment', Qt.AlignLeft)
        text_block.translation = obj.get('translation', '')
        return text_block

    @staticmethod
    def decode_qcolor(obj):
        return QtGui.QColor(
            obj.get('r', 0),
            obj.get('g', 0),
            obj.get('b', 0),
            obj.get('a', 255)
        )

    @staticmethod
    def decode_qpainterpath(obj):
        path = QtGui.QPainterPath()
        for element in obj.get('elements', []):
            if element['type'] == QtGui.QPainterPath.MoveToElement:
                path.moveTo(element['x'], element['y'])
            elif element['type'] == QtGui.QPainterPath.LineToElement:
                path.lineTo(element['x'], element['y'])
        return path

    @staticmethod
    def decode_numpy_scalar(obj):
        return np.dtype(obj['dtype']).type(obj['data'])

    @staticmethod
    def decode_tuple(obj):
        return tuple(obj['data'])

    @staticmethod
    def decode_numpy_array(obj):
        """Decodifica un array NumPy da un dizionario"""
        try:
            if '__ndarray__' in obj:
                # Nuovo formato con dati direttamente in __ndarray__
                return np.array(obj['__ndarray__'], dtype=obj.get('dtype', 'float64'))
            elif 'data' in obj:
                # Vecchio formato con dati binari
                binary_data = obj['data']
                dtype = np.dtype(obj.get('dtype', 'float64'))
                if 'shape' in obj:
                    shape = tuple(obj['shape'])
                    return np.frombuffer(binary_data, dtype=dtype).reshape(shape)
                return np.frombuffer(binary_data, dtype=dtype)
            else:
                print(f"Warning: Invalid numpy array format: {obj.keys()}")
                return np.array([])
        except Exception as e:
            print(f"Error decoding numpy array: {e}")
            return np.array([])
            
    @staticmethod
    def decode_movable_rect_item(obj):
        """Decodifica un dizionario in un oggetto MoveableRectItem"""
        return MoveableRectItem.from_dict(obj)

    @staticmethod
    def decode_textblock(obj):
        text_block = TextBlock()
        text_block.__dict__.update(obj['data'])
        return text_block

    @staticmethod
    def decode_alignment_flag(obj):
        return Qt.AlignmentFlag(obj['data'])

    @staticmethod
    def decode_outline_info(obj):
        data = obj['data']
        return OutlineInfo(
            start=data['start'],
            end=data['end'],
            color=QColor(data['color']) if isinstance(data['color'], str) else data['color'],
            width=data['width'],
            type=OutlineType(data['type']) if 'type' in data else OutlineType.Selection
        )

    @staticmethod
    def decode_layout_flag(obj):
        return Qt.LayoutDirection(obj['data'])

    @staticmethod
    def decode_alignment(obj):
        return Qt.Alignment(obj['data'])

    @staticmethod
    def decode_layout_direction(obj):
        return Qt.LayoutDirection(obj['data'])


def ensure_string_keys(d):
    if isinstance(d, dict):
        # Skip special keys that should remain as they are
        if '__class__' in d or '__error__' in d:
            return d
        return {str(k): ensure_string_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [ensure_string_keys(v) for v in d]
    return d