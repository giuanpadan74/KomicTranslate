import cv2
import numpy as np

class EllipseMaskGenerator:
    @staticmethod
    def create_ellipse_mask(image_shape, center, axes, angle=0, border_width=5, soft_edge=True, exponent=2.5):
        height, width = image_shape[:2]
        mask = np.zeros((height, width), dtype=np.float32)

        cx, cy = int(center[0]), int(center[1])
        rx, ry = int(axes[0]), int(axes[1])

        if rx <= 0 or ry <= 0:
            return mask

        angle_rad = np.deg2rad(angle)

        y, x = np.ogrid[:height, :width]
        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)

        dx = x - cx
        dy = y - cy

        x_rot = cos_a * dx + sin_a * dy
        y_rot = -sin_a * dx + cos_a * dy

        # Superellipse equation: (abs(x/rx))^n + (abs(y/ry))^n <= 1
        normalized_dist = (np.abs(x_rot) / rx) ** exponent + (np.abs(y_rot) / ry) ** exponent

        if soft_edge and border_width > 0:
            border_pixels = border_width
            inner_edge = 1.0 - border_pixels / min(rx, ry)

            mask = np.where(normalized_dist <= inner_edge ** 2, 1.0, 0.0)

            edge_region = (normalized_dist > inner_edge ** 2) & (normalized_dist <= 1.0)
            edge_distance = (normalized_dist - inner_edge ** 2) / (1.0 - inner_edge ** 2)
            mask[edge_region] = 1.0 - edge_distance[edge_region]
        else:
            mask = np.where(normalized_dist <= 1.0, 255, 0).astype(np.uint8)

        return mask

    @staticmethod
    def create_ellipse_mask_from_bbox(x1, y1, x2, y2, image_shape, rotation=0, soft_edge=True, border_width=3):
        center = ((x1 + x2) / 2, (y1 + y2) / 2)
        rx = (x2 - x1) / 2
        ry = (y2 - y1) / 2

        mask = EllipseMaskGenerator.create_ellipse_mask(
            image_shape,
            center,
            (rx, ry),
            angle=rotation,
            border_width=border_width,
            soft_edge=soft_edge
        )

        return mask

    @staticmethod
    def add_ellipse_to_mask(mask, center, axes, angle=0, value=255, soft_edge=True, border_width=2, exponent=2.5):
        height, width = mask.shape[:2]
        ellipse_mask = EllipseMaskGenerator.create_ellipse_mask(
            (height, width),
            center,
            axes,
            angle=angle,
            border_width=border_width if soft_edge else 0,
            soft_edge=soft_edge,
            exponent=exponent
        )

        if soft_edge:
            ellipse_mask = (ellipse_mask * value).astype(mask.dtype)
        else:
            ellipse_mask = (ellipse_mask > 0).astype(mask.dtype) * value

        if mask.dtype != ellipse_mask.dtype:
            ellipse_mask = ellipse_mask.astype(mask.dtype)

        return cv2.bitwise_or(mask, ellipse_mask)

    @staticmethod
    def apply_rotation_to_ellipse_params(center, axes, angle, image_shape):
        height, width = image_shape[:2]
        cx, cy = center

        angle_rad = np.deg2rad(angle)
        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)

        rx, ry = axes

        corners = np.array([
            [-rx, -ry],
            [rx, -ry],
            [-rx, ry],
            [rx, ry]
        ])

        rotated_corners = np.zeros_like(corners)
        for i, (x, y) in enumerate(corners):
            rotated_corners[i, 0] = cos_a * x - sin_a * y + cx
            rotated_corners[i, 1] = sin_a * x + cos_a * y + cy

        min_x = max(0, int(np.min(rotated_corners[:, 0])))
        max_x = min(width - 1, int(np.max(rotated_corners[:, 0])))
        min_y = max(0, int(np.min(rotated_corners[:, 1])))
        max_y = min(height - 1, int(np.max(rotated_corners[:, 1])))

        return (min_x, min_y), (max_x, max_y)

    @staticmethod
    def get_ellipse_bounding_rect(center, axes, angle, image_shape):
        height, width = image_shape[:2]
        cx, cy = center
        rx, ry = axes

        angle_rad = np.deg2rad(angle)
        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)

        ux = rx * cos_a
        uy = rx * sin_a
        vx = ry * cos_a
        vy = ry * sin_a

        half_width = np.sqrt(ux ** 2 + uy ** 2)
        half_height = np.sqrt(vx ** 2 + vy ** 2)

        x1 = max(0, int(cx - half_width))
        y1 = max(0, int(cy - half_height))
        x2 = min(width - 1, int(cx + half_width))
        y2 = min(height - 1, int(cy + half_height))

        return x1, y1, x2, y2

    @staticmethod
    def is_point_in_ellipse(point, center, axes, angle=0, exponent=2.5, scale=1.1):
        """
        Checks if a point (x, y) is inside a superellipse defined by center, axes, 
        rotation angle, and exponent.
        
        Args:
            point (tuple): (x, y) coordinates of the point.
            center (tuple): (cx, cy) coordinates of the ellipse center.
            axes (tuple): (rx, ry) lengths of the semi-major and semi-minor axes.
            angle (float): Rotation angle in degrees (clockwise).
            exponent (float): Exponent for the superellipse equation. 2.0 = ellipse, >2.0 = bubble-like.
            scale (float): Scale factor for the axes. >1.0 expands the selection.
            
        Returns:
            bool: True if the point is inside or on the boundary of the superellipse.
        """
        # Fast-path Rust (parita 2000/2000 verificata). Fallback Python invariato.
        try:
            from modules._rs_bridge import rs_is_point_in_ellipse

            rs_result = rs_is_point_in_ellipse(point, center, axes, angle, exponent, scale)
            if rs_result is not None:
                return rs_result
        except Exception:
            pass
        cx, cy = center
        rx, ry = axes[0] * scale, axes[1] * scale
        px, py = point

        if rx <= 0 or ry <= 0:
            return False

        # Convert angle to radians
        angle_rad = np.deg2rad(angle)
        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)

        # Shift point relative to center
        dx = px - cx
        dy = py - cy

        # Apply inverse rotation
        x_rot = cos_a * dx + sin_a * dy
        y_rot = -sin_a * dx + cos_a * dy

        # Superellipse equation: (abs(x/rx))^n + (abs(y/ry))^n <= 1
        normalized_dist = (np.abs(x_rot) / rx) ** exponent + (np.abs(y_rot) / ry) ** exponent
        
        return normalized_dist <= 1.0
