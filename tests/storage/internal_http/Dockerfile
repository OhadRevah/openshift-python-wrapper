FROM nginx

ARG IMAGE_DIR=/tmp/shared/images

RUN mkdir -p $IMAGE_DIR

COPY images $IMAGE_DIR

RUN rm -f /etc/nginx/nginx.conf

COPY nginx.conf /etc/nginx/

COPY htpasswd /etc/nginx/

EXPOSE 80

EXPOSE 81

EXPOSE 82

ENTRYPOINT nginx
