# app/services/local_image_service.py
import os
import shutil
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from datetime import datetime
import uuid
from PIL import Image

class LocalImageService:
    UPLOAD_DIR = "uploads/consigeeprofilimage"
    
    @classmethod
    def ensure_upload_dir(cls):
        """Ensure upload directory exists"""
        Path(cls.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def validate_image(cls, file: UploadFile) -> bool:
        """Validate image file"""
        # Check file extension
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Check file size (max 5MB)
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size too large. Maximum size is 5MB"
            )
        
        return True
    
    @classmethod
    async def save_profile_image(cls, file: UploadFile, user_id: str) -> str:
        """
        Save profile image locally and return the URL path
        """
        cls.ensure_upload_dir()
        
        # Validate image
        cls.validate_image(file)
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = os.path.splitext(file.filename)[1]
        filename = f"profile_{user_id}_{timestamp}{file_extension}"
        
        # Save path
        file_path = os.path.join(cls.UPLOAD_DIR, filename)
        
        try:
            # Save file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Optional: Resize image using PIL
            with Image.open(file_path) as img:
                # Resize to 500x500 if larger
                if img.width > 500 or img.height > 500:
                    img.thumbnail((500, 500))
                    img.save(file_path, optimize=True, quality=85)
            
            # Return URL path (for API access)
            return f"/uploads/profilimage/{filename}"
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save image: {str(e)}"
            )
    
    @classmethod
    def delete_profile_image(cls, image_url: str):
        """Delete profile image from local storage"""
        if not image_url:
            return
        
        # Extract filename from URL
        filename = os.path.basename(image_url)
        file_path = os.path.join(cls.UPLOAD_DIR, filename)
        
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Failed to delete image: {e}")
    
    @classmethod
    async def update_profile_image(cls, file: UploadFile, user_id: str, old_image_url: str = None) -> str:
        """Update profile image - delete old and save new"""
        # Delete old image if exists
        if old_image_url:
            cls.delete_profile_image(old_image_url)
        
        # Save new image
        return await cls.save_profile_image(file, user_id)