# Disclaimer: This code is for learning and research purposes only. Users should abide by the following principles:
# 1. Not for any commercial purposes.
# 2. When using, you should comply with the terms of use and robots.txt rules of the target platform.
# 3. Do not conduct large-scale crawling or cause operational interference to the platform.
# 4. The request frequency should be reasonably controlled to avoid unnecessary burden on the target platform.
# 5. May not be used for any illegal or inappropriate purposes.
#   
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# By using this code, you agree to abide by the above principles and all terms in LICENSE.


# Kuaishou’s data transmission is based on GraphQL
# This class is responsible for obtaining some GraphQL schema
from typing import Dict


class KuaiShouGraphQL:
    graphql_queries: Dict[str, str]= {}

    def __init__(self):
        self.graphql_dir = "media_platform/kuaishou/graphql/"
        self.load_graphql_queries()

    def load_graphql_queries(self):
        graphql_files = ["search_query.graphql", "video_detail.graphql", "comment_list.graphql", "vision_profile.graphql","vision_profile_photo_list.graphql","vision_profile_user_list.graphql","vision_sub_comment_list.graphql"]

        for file in graphql_files:
            with open(self.graphql_dir + file, mode="r") as f:
                query_name = file.split(".")[0]
                self.graphql_queries[query_name] = f.read()

    def get(self, query_name: str) -> str:
        return self.graphql_queries.get(query_name, "Query not found")
