FROM vllm/vllm-openai:v0.6.3

ENV MODEL_PATH=/model
ENV PORT=8080

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]