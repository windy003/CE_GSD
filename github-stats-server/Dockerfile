FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt   &&   apt update -y  && apt upgrade -y  &&   apt install git -y

COPY . .

# 创建指定UID的用户（使用1000作为示例，这是很多Linux系统默认用户的UID）
RUN useradd -u 1000 -m myuser && \
    chown -R myuser:myuser /app && \
    chmod -R 755 /app 


USER myuser

