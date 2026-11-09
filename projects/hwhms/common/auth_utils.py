

from typing import Optional

from fastapi.requests import Request
from fastapi.responses import JSONResponse

auth_keys = [
        "Bearer lNTZIiZXf_-uwfTE1z2oQM5RekCl94GuiHFTb3ntnK5XAguc-SWrB6hQBUHybggHFYko-iPDAGexPgPdexINizhEQGBGyDeBlOOcFxZQvTEI52tfBeUfJhkV-ADH57QlLrjJxtSV8VUsVIC1hFSB61vOF4rNEDi2kwoc6I",
        "Bearer lNTZIiZXf_-uwfTE1z2oQM5RekCl94GuiHFTb3ntnK5XAguc-SWrB6hQBvdYsTMy5LHgW-iPDAGexPgPdexINizhEQGBonRnX1jTzlKbEFxZQvTEI52tfBeUfJhkV-ADH57QlLrjJxtSV8VUsVIC1hFSB61vOF4rNEDi2kwoc6I"
    ]

def verify_authorization(request: Request) -> Optional[JSONResponse]:
    """
    验证请求的Authorization header
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        如果认证失败，返回错误的JSONResponse；如果认证成功，返回None
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return JSONResponse(content={"error": "Invalid authorization"}, status_code=401)
    
    if auth_header not in auth_keys:
        return JSONResponse(content={"error": "Invalid authorization"}, status_code=401)
    
    return None