# QQ 音乐搜索接口文档

## 接口概述

**功能说明**: 根据输入的关键字搜索歌曲、专辑、MV、歌单、电台

**命令字**: `fcg_music_custom_search.fcg`

**接口地址**: `https://openrpc.music.qq.com/rpc_proxy/fcgi-bin/music_open_api.fcg`

**请求方式**: GET/POST

**返回格式**: JSON

## 接口原子能力分析

该接口支持多种音乐搜索原子能力，通过 `t` 参数的不同值实现不同的搜索功能。

### 1. 单曲搜索

**原子能力**: 搜索指定关键词的音乐歌曲

**调用参数**:
- `opi_cmd`: `fcg_music_custom_search.fcg` (必填)
- `w`: 搜索关键词（必填，对于含有;等特殊字符的，建议urlencode）
- `t`: `0`（搜索类型为单曲）
- `p`: 页码（可选，默认为1，最大5页）
- `num`: 每页数量（可选，默认为20，最大值50）

**鉴权参数**（必填）:
- `app_id`: 应用ID
- `timestamp`: 时间戳
- `sign`: 签名
- `login_type`: 登录类型（通常为6）
- `qqmusic_open_appid`: QQ音乐开放应用ID
- `qqmusic_open_id`: QQ音乐开放ID
- `qqmusic_access_token`: QQ音乐访问令牌

**调用示例**:
```
https://openrpc.music.qq.com/rpc_proxy/fcgi-bin/music_open_api.fcg?opi_cmd=fcg_music_custom_search.fcg&app_id=xxxxxxxxxxx&timestamp=1555067641&sign=1ebf9d123a74446bb77a2ec2e9533c5f&login_type=6&qqmusic_open_appid=xxxxxxxxxxx&qqmusic_open_id=xxxxxxxxxxx&qqmusic_access_token=xxxxxxxxxxx&w=周杰伦&p=1&num=10&t=0
```

### 2. 歌单搜索

**原子能力**: 搜索指定关键词的歌单

**调用参数**:
- `opi_cmd`: `fcg_music_custom_search.fcg` (必填)
- `w`: 搜索关键词（必填）
- `t`: `3`（搜索类型为歌单）
- `p`: 页码（可选，默认为1，最大5页）
- `num`: 每页数量（可选，默认为20，最大值50）

**调用示例**:
```
https://openrpc.music.qq.com/rpc_proxy/fcgi-bin/music_open_api.fcg?opi_cmd=fcg_music_custom_search.fcg&app_id=xxxxxxxxxxx&timestamp=1555067641&sign=1ebf9d123a74446bb77a2ec2e9533c5f&login_type=6&qqmusic_open_appid=xxxxxxxxxxx&qqmusic_open_id=xxxxxxxxxxx&qqmusic_access_token=xxxxxxxxxxx&w=流行&p=1&num=10&t=3
```

### 3. 专辑搜索

**原子能力**: 搜索指定关键词的音乐专辑

**调用参数**:
- `opi_cmd`: `fcg_music_custom_search.fcg` (必填)
- `w`: 搜索关键词（必填）
- `t`: `8`（搜索类型为专辑）
- `p`: 页码（可选，默认为1，最大5页）
- `num`: 每页数量（可选，默认为20，最大值50）

**调用示例**:
```
https://openrpc.music.qq.com/rpc_proxy/fcgi-bin/music_open_api.fcg?opi_cmd=fcg_music_custom_search.fcg&app_id=xxxxxxxxxxx&timestamp=1555067641&sign=1ebf9d123a74446bb77a2ec2e9533c5f&login_type=6&qqmusic_open_appid=xxxxxxxxxxx&qqmusic_open_id=xxxxxxxxxxx&qqmusic_access_token=xxxxxxxxxxx&w=告白气球&p=1&num=10&t=8
```

### 4. MV搜索

**原子能力**: 搜索指定关键词的音乐视频（MV）

**调用参数**:
- `opi_cmd`: `fcg_music_custom_search.fcg` (必填)
- `w`: 搜索关键词（必填）
- `t`: `12`（搜索类型为MV）
- `p`: 页码（可选，默认为1，最大5页）
- `num`: 每页数量（可选，默认为20，最大值50）

**调用示例**:
```
https://openrpc.music.qq.com/rpc_proxy/fcgi-bin/music_open_api.fcg?opi_cmd=fcg_music_custom_search.fcg&app_id=xxxxxxxxxxx&timestamp=1555067641&sign=1ebf9d123a74446bb77a2ec2e9533c5f&login_type=6&qqmusic_open_appid=xxxxxxxxxxx&qqmusic_open_id=xxxxxxxxxxx&qqmusic_access_token=xxxxxxxxxxx&w=告白气球&p=1&num=10&t=12
```

### 5. 电台搜索

**原子能力**: 搜索指定关键词的电台

**调用参数**:
- `opi_cmd`: `fcg_music_custom_search.fcg` (必填)
- `w`: 搜索关键词（必填）
- `t`: `15`（搜索类型为电台）
- `p`: 页码（可选，默认为1，最大5页）
- `num`: 每页数量（可选，默认为20，最大值50）

**调用示例**:
```
https://openrpc.music.qq.com/rpc_proxy/fcgi-bin/music_open_api.fcg?opi_cmd=fcg_music_custom_search.fcg&app_id=xxxxxxxxxxx&timestamp=1555067641&sign=1ebf9d123a74446bb77a2ec2e9533c5f&login_type=6&qqmusic_open_appid=xxxxxxxxxxx&qqmusic_open_id=xxxxxxxxxxx&qqmusic_access_token=xxxxxxxxxxx&w=音乐电台&p=1&num=10&t=15
```

## 通用参数说明

### 必填参数

| 参数名 | 类型 | 说明 |
|--------|------|:------|
| opi_cmd | string | 命令字，固定为 `fcg_music_custom_search.fcg` |
| w | string | 搜索关键词（对于含有;等特殊字符的，建议urlencode） |

### 鉴权参数（必填）

| 参数名 | 类型 | 说明 |
|--------|------|:------|
| app_id | string | 应用ID |
| timestamp | int | 时间戳 |
| sign | string | 签名 |
| login_type | int | 登录类型（通常为6） |
| qqmusic_open_appid | string | QQ音乐开放应用ID |
| qqmusic_open_id | string | QQ音乐开放ID |
| qqmusic_access_token | string | QQ音乐访问令牌 |

### 可选参数

| 参数名 | 类型 | 说明 | 默认值 | 限制 |
|--------|------|:------|--------|:------|
| t | int | 搜索类型 | 0 | 见下文搜索类型表 |
| p | int | 页码 | 1 | 最大5页 |
| num | int | 每页返回数量 | 20 | 最大值50 |

## 搜索类型（t参数）完整列表

| t值 | 说明 | 备注 |
|-----|------|:------|
| 0 | 单曲搜索 | 最常用的搜索类型 |
| 3 | 歌单搜索 | - |
| 8 | 专辑搜索 | - |
| 12 | MV搜索 | - |
| 15 | 电台搜索 | - |

## 返回数据格式

### 通用返回字段

| 参数名 | 类型 | 说明 |
|--------|------|:------|
| ret | int | 返回码 |
| sub_ret | int | 详情返回码，用于具体定位错误，一般为0 |
| msg | string | 如果错误，返回错误信息 |
| cur_num | int | 当前返回个数 |
| cur_page | int | 当前页码 |
| total_num | int | 该搜索词可以搜到的总结果数 |
| keyword | string | 搜索词 |
| list | array | 搜索结果列表 |
| user_own_rule | int | 表示用户拥有接口的权限。0：只浏览；1：可播放 |
| has_more | bool | 是否有下一页 |
| zhida | object | 直达结果结构体 |

**注意**: 对于 `user_own_rule=0`（即免费用户，且只浏览权限），只返回只读数据，并且部分字段会被置0或置空。

### 单曲搜索返回字段（list数组元素）

| 参数名 | 类型 | 说明 |
|--------|------|:------|
| song_id | int | 歌曲id |
| song_mid | string | 歌曲mid |
| song_name | string | 歌曲名 |
| song_title | string | 歌曲标题 |
| singer_id | string | 歌手id |
| singer_mid | string | 歌手mid |
| singer_name | string | 歌手名 |
| singer_pic | string | 歌手图片 |
| album_id | uint64 | 专辑id |
| album_mid | string | 专辑mid |
| album_name | string | 专辑名 |
| album_pic | string | 专辑封面 |
| album_pic_150x150 | string | 图片规格150x150专辑封面 |
| album_pic_300x300 | string | 图片规格300x300专辑封面 |
| album_pic_500x500 | string | 图片规格500x500专辑封面 |
| song_play_time | int | 播放总时间（单位秒） |
| song_h5_url | string | H5分享页面url |
| genre | string | 流派 |
| language | string | 语言 |
| author | string | 曲作者 |
| playable | int | 1：表示能播放，0：表示不能播放 |
| vip | int | 1：vip歌曲，0：普通歌曲 |
| isdigital_album | int | 是否是数字专辑，0不是 1是 |
| origin | int | 1：原唱，0：其他 |
| match_lyric | string | 单曲搜索时，如果是歌词召回的，返回匹配到的歌词 |
| unplayable_code | int | 该字段标识不能播放的原因代码 |
| unplayable_msg | string | 不能播放原因描述语 |
| k_song_id | uint64 | K歌id |
| k_song_mid | string | K歌mid |
| mv_id | int | MV id |
| try_begin | int | 试听开始位置，单位ms |
| try_end | int | 试听结束位置，单位ms |
| try_file_size | int | 试听流媒体大小，单位byte |
| try_playable | int | 试听权限，1：表示有试听权限，0：表示没有 |
| try_30s_url | string | 试听流媒体url |
| song_play_url | string | 流畅品质流媒体url |
| song_play_url_standard | string | 标准品质流媒体url |
| song_play_url_hq | string | 高品质流媒体url |
| song_play_url_sq | string | 无损品质流媒体url |
| song_size | int | 流畅品质流媒体大小，单位字节 |
| song_size_standard | int | 标准品质流媒体大小，单位字节 |
| song_size_hq | int | 高品质流媒体大小，单位字节 |
| song_size_sq | int | 无损品质流媒体大小，单位字节 |

### 直达结果（zhida字段）

| 参数名 | 类型 | 说明 |
|--------|------|:------|
| id | long | 根据type确定 |
| type | int | 直达类型 1：歌手 2：专辑 4：歌单 9：排行榜 其他可暂不处理 |
| title | string | 标题 |
| sub_title | string | 副标题 |
| pic | string | type对应的图片 |

### 成功响应示例

```json
{
  "ret": 0,
  "sub_ret": 0,
  "msg": "success",
  "cur_num": 10,
  "cur_page": 1,
  "total_num": 100,
  "keyword": "周杰伦",
  "list": [
    {
      "song_id": 123456,
      "song_mid": "001fXNWa3t8EQQ",
      "song_name": "告白气球",
            "song_title": "告白气球",
      "singer_id": "002J4UUk29y8BY",
      "singer_mid": "002J4UUk29y8BY",
      "singer_name": "周杰伦",
      "singer_pic": "http://...",
      "album_pic": "http://.../album_pic_500x500.jpg",
      "album_pic_150x150": "http://.../album_pic_150x150.jpg",
      "album_pic_300x300": "http://.../album_pic_300x300.jpg",
      "album_pic_500x500": "http://.../album_pic_500x500.jpg",
      "song_play_time": 215,
      "song_h5_url": "http://...",
      "genre": "流行",
      "language": "国语",
      "author": "周杰伦",
      "playable": 1,
      "vip": 0,
      "isdigital_album": 0,
      "origin": 1,
      "unplayable_code": 0,
      "unplayable_msg": "",
      "k_song_id": 0,
      "k_song_mid": "",
      "mv_id": 0,
      "try_begin": 0,
      "try_end": 0,
      "try_file_size": 0,
      "try_playable": 0,
      "try_30s_url": "",
      "song_play_url": "http://...",
      "song_play_url_standard": "http://...",
      "song_play_url_hq": "http://...",
      "song_play_url_sq": "http://...",
      "song_size": 1234567,
      "song_size_standard": 2345678,
      "song_size_hq": 3456789,
      "song_size_sq": 4567890
    }
  ],
  "user_own_rule": 1,
  "has_more": true,
  "zhida": {
    "id": 123,
    "type": 1,
    "title": "周杰伦",
    "sub_title": "华语流行天王",
    "pic": "http://..."
  }
}
```

### 错误响应示例

```json
{
  "ret": 1001,
  "sub_ret": 0,
  "msg": "非法参数app_id",
  "ts": 1774340549110
}
```

## 错误码说明

| ret | sub_ret | 说明 |
|-----|---------|:------|
| 0 | 0 | 成功 |
| -4 | 0 | 搜索失败 |
| 100434 | -1 | 页数和数量超出范围 |
| 100434 | -2 | 搜索类型错误 |
| 100434 | -3 | 关键词太短 |
| 100500 | -6 | 过滤歌曲失败 |
| 100500 | -8 | 搜索结果为空 |
| 100500 | 0 | 搜索非法词语 |
| 1001 | 0 | 非法参数 |

## 注意事项

1. **编码格式**: URL参数需要进行URL编码，对于含有;等特殊字符的搜索词，建议使用urlencode
2. **分页限制**: 单曲、专辑、MV、歌单搜索页码最大5页，每页数量最大50
3. **权限控制**: `user_own_rule=0` 表示只浏览权限，部分字段会被置0或置空
4. **鉴权参数**: 所有请求都需要包含完整的鉴权参数（app_id、timestamp、sign等）
5. **签名验证**: sign参数需要根据特定的签名算法生成
6. **试听限制**: 免费用户只能试听部分歌曲，试听时间由try_begin和try_end参数控制
7. **音质选择**: 返回数据包含多种音质的播放地址，可根据用户权限选择合适的音质

## 使用建议

1. **搜索歌曲**: 使用 `t=0`，这是最常用的搜索功能
2. **精确搜索**: 可以组合歌手名和歌曲名进行搜索，如 `w=周杰伦+告白气球`
3. **分页加载**: 使用 `p` 和 `num` 参数实现分页加载，注意页码最大为5
4. **结果过滤**: 可以在客户端根据返回数据进行二次过滤
5. **缓存策略**: 建议对热门搜索结果进行缓存，减少接口调用
6. **权限判断**: 根据 `user_own_rule` 和 `playable` 字段判断是否可以播放
7. **音质选择**: 根据用户权限和设备情况选择合适的音质（流畅/标准/高品质/无损）
8. **直达结果**: 优先处理 `zhida` 字段，提供更精准的搜索结果

## 相关接口

基于搜索结果中的song_id/song_mid，可以进一步调用以下接口获取详细信息：

- 获取歌曲详情: `fcg_music_get_song_info.fcg`
- 获取歌曲播放地址: `fcg_music_get_song_url.fcg`
- 获取歌词: `fcg_music_get_lyric.fcg`
- 获取专辑详情: `fcg_music_get_album_info.fcg`
- 获取MV信息: `fcg_music_get_mv_info.fcg`
- 获取歌单详情: `fcg_music_get_playlist_info.fcg`
