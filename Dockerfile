FROM python:3.13-slim

ARG APP_NAME=sgm-api
ENV APP_NAME=${APP_NAME} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8007

EXPOSE ${PORT}

WORKDIR /var/${APP_NAME}

COPY . /var/${APP_NAME}

RUN pip install --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

RUN chmod +x /var/${APP_NAME}/entrypoint.sh

ENTRYPOINT bash /var/${APP_NAME}/entrypoint.sh
