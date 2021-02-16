FROM tiangolo/uwsgi-nginx-flask

RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
RUN sed -i 's/archive.ubunutu.com/opentuna.cn/g' /etc/apt/sources.list
RUN sed -i 's/security.ubunutu.com/opentuna.cn/g' /etc/apt/sources.list

RUN pip3 install redis requests

COPY ./app /app