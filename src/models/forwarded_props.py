from __future__ import annotations

from pydantic import BaseModel, Field


class ForwardedProps(BaseModel):
    """Expected format for `forwardedProps` sent by the frontend in RunAgentInput.

    The frontend should send camelCase keys:
    ```json
    {
      "forwardedProps": {
        "datasetIds": ["id1", "id2"]
      }
    }
    ```
    """

    dataset_ids: list[str] = Field(
        default_factory=list,
        alias="datasetIds",
        description="List of dataset IDs to scope document searches. "
        "All tools that search documents will restrict results to these datasets.",
    )

    model_config = {"populate_by_name": True}
