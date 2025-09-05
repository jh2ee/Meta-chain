FROM python:3.11-slim
WORKDIR /app


# 패키지 설치
RUN pip install --no-cache-dir fastapi uvicorn[standard] jinja2 \
web3==6.19.0 py-solc-x==1.1.1 python-multipart


# 소스 복사
COPY app.py /app/app.py
COPY contracts /app/contracts
COPY templates /app/templates
COPY static /app/static


EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]