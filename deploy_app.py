from main import app
from fastapi import HTTPException
from api.question_engine import status
@app.get('/ready')
def ready():
    if status()['state']!='ready':
        raise HTTPException(status_code=503,detail='Question service is preparing')
    return {'status':'ready'}
