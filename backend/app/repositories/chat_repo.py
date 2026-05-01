import json
from sqlalchemy.orm import Session
from app.db.models import Chat, Message
from app.utils.cloudinary_tool import upload_image_to_cloud

class ChatRepository:
    @staticmethod
    def get_by_id(db: Session, chat_id: int, user_id: int):
        return db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user_id).first()

    @staticmethod
    def get_all_by_user(db: Session, user_id: int):
        return db.query(Chat).filter(Chat.user_id == user_id).order_by(Chat.id.desc()).all()

    @staticmethod
    def create_chat(db: Session, user_id: int, title: str = "New Chat"):
        new_chat = Chat(user_id=user_id, title=title)
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)
        return new_chat

    @staticmethod
    def update_title(db: Session, chat_id: int, new_title: str):
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat:
            chat.title = new_title
            db.commit()
        return chat

    @staticmethod
    def delete_chat(db: Session, chat_id: int, user_id: int):
        chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user_id).first()
        if chat:
            # Cascade delete agar model mein nahi hai toh manually messages delete karein
            db.query(Message).filter(Message.chat_id == chat_id).delete()
            db.delete(chat)
            db.commit()
            return True
        return False

    @staticmethod
    def add_message(db: Session, chat_id: int, role: str, content: str, image_data_list: list = None):
        cloud_urls = []
        if image_data_list:
            for img_base64 in image_data_list:
                url = upload_image_to_cloud(img_base64, folder="chat_messages")
                if url:
                    cloud_urls.append(url)
    
        # DB mein ab URLs ki list (JSON string) save hogi, heavy Base64 nahi
        db_image_data = json.dumps(cloud_urls) if cloud_urls else None
        new_msg = Message(chat_id=chat_id, role=role, content=content, image_data=db_image_data)
        db.add(new_msg)
        db.commit()
        return new_msg
    
    @staticmethod
    def update_pdf_context(db: Session, chat_id: int, text: str):
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat:
            chat.pdf_context = text
            db.commit()
            return chat
        return None
    
    @staticmethod
    def save_ai_log(db: Session, task: str, prompt: str, response: str, user_id: int = None):
        log = AILog(user_id=user_id, task=task, prompt=prompt, response=response)
        db.add(log)
        db.commit()
        
    @staticmethod
    def get_history(db: Session, chat_id: int, limit: int = 10):
        history = db.query(Message).filter(Message.chat_id == chat_id)\
                .order_by(Message.id.desc()).limit(limit).all()
        history.reverse()
        return history
    
    @staticmethod
    def delete_messages_after(db: Session, chat_id: int, user_id: int, after_index: int):
        messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.id.asc()).all()
        if after_index < len(messages):
            target_msg_id = messages[after_index].id
            
            # Security Check: user_id verify karna lazmi hai
            db.query(Message).filter(
                Message.chat_id == chat_id,
                Message.id >= target_msg_id
            ).delete(synchronize_session=False)
            db.commit()