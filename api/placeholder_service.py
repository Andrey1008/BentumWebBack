import hashlib

class PlaceholderGenerator:
    """Генератор плейсхолдеров для аватаров и баннеров через CSS"""
    
    @staticmethod
    def get_initials(fullname):
        """Получает инициалы из полного имени"""
        if not fullname:
            return "U"
        
        parts = fullname.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        elif len(parts) == 1:
            return parts[0][:2].upper() if len(parts[0]) > 1 else parts[0].upper()
        else:
            return "U"
    
    @staticmethod
    def get_avatar_placeholder_data(fullname):
        """Возвращает данные для CSS аватара"""
        initials = PlaceholderGenerator.get_initials(fullname)
        
        return {
            "type": "avatar",
            "initials": initials,
            "background": "linear-gradient(135deg, rgb(16, 185, 129) 0%, rgb(20, 184, 166) 100%)",
            "color": "#ffffff",
            "font_size": "300%",
            "font_weight": "600"
        }
    
    @staticmethod
    def get_banner_placeholder_data():
        """Возвращает данные для CSS баннера"""
        return {
            "type": "banner", 
            "background": "linear-gradient(135deg, rgb(16, 185, 129) 0%, rgb(20, 184, 166) 100%)",
            "pattern": None
        }
    
    @staticmethod
    def get_placeholder_css_class(media_type, fullname=None):
        """Генерирует CSS класс для плейсхолдера"""
        if media_type == 'avatar':
            data = PlaceholderGenerator.get_avatar_placeholder_data(fullname or '')
            return f"avatar-placeholder-{hash(fullname or '') % 1000}"
        elif media_type == 'banner':
            return "banner-placeholder"
        return None
    
    @staticmethod
    def generate_placeholder_css(user, media_type):
        """Генерирует CSS правила для плейсхолдера пользователя"""
        if media_type == 'avatar':
            data = PlaceholderGenerator.get_avatar_placeholder_data(user.fullname)
            class_name = f"avatar-placeholder-{hash(user.student_code) % 1000}"
            
            css_rules = f"""
            .{class_name} {{
                background: {data['background']};
                color: {data['color']};
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: {data['font_size']};
                font-weight: {data['font_weight']};
                text-transform: uppercase;
                user-select: none;
            }}
            .{class_name}::before {{
                content: '{data['initials']}';
            }}
            """
            
            return {
                "class_name": class_name,
                "css_rules": css_rules,
                "data": data
            }
            
        elif media_type == 'banner':
            data = PlaceholderGenerator.get_banner_placeholder_data()
            
            css_rules = f"""
            .banner-placeholder {{
                background: {data['background']};
                position: relative;
                overflow: hidden;
            }}
            """
            
            return {
                "class_name": "banner-placeholder",
                "css_rules": css_rules,
                "data": data
            }
        
        return None
