# This file is no longer needed for Managed SFT approach.
# The training script runs inside Google's managed container.
# 
# If you need custom training logic in the future, refer to:
# https://cloud.google.com/vertex-ai/generative-ai/docs/models/open-model-tuning

raise NotImplementedError(
    "This file is deprecated. Use Managed SFT instead:\n"
    "  python -m temporary.ft_vertex_job --launch"
)
