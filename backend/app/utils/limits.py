from fastapi import HTTPException
from app.db.models import User, UserPlan

def check_user_usage_limit(user: User, tool_type: str):
    """
    tool_type: 'image' or 'search'
    """
    if user.plan == UserPlan.FREE:
        if tool_type == "image" and user.image_limit <= 0:
            raise HTTPException(status_code=403, detail="Free image limit reached. Upgrade to Standard!")
        if tool_type == "search" and user.search_limit <= 0:
            raise HTTPException(status_code=403, detail="Free search limit reached. Upgrade to Pro!")
    
    # Standard/Pro plans ke liye yahan unlimited ya high limits add kar sakte hain
    return True

def decrement_user_limit(db, user: User, tool_type: str):
    """Tool use hone ke baad limit kam karein"""
    if tool_type == "image":
        user.image_limit -= 1
    elif tool_type == "search":
        user.search_limit -= 1
    db.commit()