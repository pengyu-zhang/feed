You write a daily reading digest for one reader: a machine learning researcher whose first language is Chinese. He wants to understand each post well in Chinese without opening the original. Below are $N new blog posts. If a post's text is cut off, cover what is there and do not invent the rest.

$COMMON

Reply with ONLY a JSON array, one object per post, in the same order, each with keys "id", "brief_zh", "background_zh", "points_zh", "conclusion_zh", "brief_en", "background_en", "points_en", "conclusion_en", "topics". No other text.

POSTS:
$POSTS
