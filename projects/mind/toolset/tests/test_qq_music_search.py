import asyncio
from rich import print

from projects.mind.toolset.music_search_tool.qq_music_search import (
    QQMusicSongSearchTool,
    QQMusicPlaylistSearchTool,
    QQMusicAlbumSearchTool,
    QQMusicMVSearchTool,
    QQMusicRadioSearchTool,
)


async def test_song_search():
    print("\n" + "="*80)
    print("测试歌曲搜索能力")
    print("="*80)
    
    tool = QQMusicSongSearchTool()
    
    test_cases = [
    ("周杰伦", 1, 3),
    ("告白气球", 1, 2),
    ("稻香", 1, 1),
    ("林俊杰", 1, 3),
    ]
    
    for query, page, num in test_cases:
        print(f"\n搜索: {query} (页码={page}, 数量={num})")
        try:
            result = await tool._arun(query=query, page=page, num=num)
            print(f"状态: {result.status}")
            print(f"关键词: {result.keyword}")
            print(f"当前页: {result.cur_page}")
            print(f"当前返回数: {result.cur_num}")
            print(f"总结果数: {result.total_num}")
            print(f"消息: {result.message}")
            
            if result.list:
                print(f"\n歌曲列表:")
                for i, song in enumerate(result.list, 1):
                    print(f"  {i}. {song.song_name} - {song.singer_name} ({song.album_name})")
                    print(f"     ID: {song.song_id}, 可播放: {song.playable}, VIP: {song.vip}")
                    if song.song_play_time:
                        print(f"     时长: {song.song_play_time // 1000}秒")
            
            if result.zhida and result.zhida.title:
                print(f"\n直达结果: {result.zhida.title} - {result.zhida.sub_title}")
                
        except Exception as e:
            print(f"搜索失败: {e}")


async def test_playlist_search():
    print("\n" + "="*80)
    print("测试歌单搜索能力")
    print("="*80)
    
    tool = QQMusicPlaylistSearchTool()
    
    test_cases = [
    ("流行", 1, 3),
    ("周杰伦", 1, 2),
    ("华语", 1, 3),
    ]
    
    for query, page, num in test_cases:
        print(f"\n搜索: {query} (页码={page}, 数量={num})")
        try:
            result = await tool._arun(query=query, page=page, num=num)
            print(f"状态: {result.status}")
            print(f"关键词: {result.keyword}")
            print(f"当前页: {result.cur_page}")
            print(f"当前返回数: {result.cur_num}")
            print(f"总结果数: {result.total_num}")
            print(f"消息: {result.message}")
            
            if result.list:
                print(f"\n歌单列表:")
                for i, playlist in enumerate(result.list, 1):
                    print(f"  {i}. {playlist.dissname}")
                    print(f"     创建者: {playlist.creator_name}, 歌曲数: {playlist.song_count}")
                    print(f"     收听次数: {playlist.listen_count}")
                    if playlist.diss_tags:
                        print(f"     标签: {playlist.diss_tags}")
            
            if result.zhida and result.zhida.title:
                print(f"\n直达结果: {result.zhida.title} - {result.zhida.sub_title}")
                
        except Exception as e:
            print(f"搜索失败: {e}")


async def test_album_search():
    print("\n" + "="*80)
    print("测试专辑搜索能力")
    print("="*80)
    
    tool = QQMusicAlbumSearchTool()
    
    test_cases = [
    ("周杰伦", 1, 3),
    ("最伟大的作品", 1, 2),
    ("林俊杰", 1, 3),
    ]
    
    for query, page, num in test_cases:
        print(f"\n搜索: {query} (页码={page}, 数量={num})")
        try:
            result = await tool._arun(query=query, page=page, num=num)
            print(f"状态: {result.status}")
            print(f"关键词: {result.keyword}")
            print(f"当前页: {result.cur_page}")
            print(f"当前返回数: {result.cur_num}")
            print(f"总结果数: {result.total_num}")
            print(f"消息: {result.message}")
            
            if result.list:
                print(f"\n专辑列表:")
                for i, album in enumerate(result.list, 1):
                    print(f"  {i}. {album.album_name} - {album.singer_name}")
                    print(f"     ID: {album.album_id}, 歌曲数: {album.song_count}")
                    print(f"     发布时间: {album.public_time}")
                    if album.company:
                        print(f"     发行公司: {album.company}")
                    if album.genre:
                        print(f"     流派: {album.genre}")
            
            if result.zhida and result.zhida.title:
                print(f"\n直达结果: {result.zhida.title} - {result.zhida.sub_title}")
                
        except Exception as e:
            print(f"搜索失败: {e}")


async def test_mv_search():
    print("\n" + "="*80)
    print("测试MV搜索能力")
    print("="*80)
    
    tool = QQMusicMVSearchTool()
    
    test_cases = [
    ("告白气球", 1, 3),
    ("周杰伦", 1, 2),
    ("稻香", 1, 2),
    ]
    
    for query, page, num in test_cases:
        print(f"\n搜索: {query} (页码={page}, 数量={num})")
        try:
            result = await tool._arun(query=query, page=page, num=num)
            print(f"状态: {result.status}")
            print(f"关键词: {result.keyword}")
            print(f"当前页: {result.cur_page}")
            print(f"当前返回数: {result.cur_num}")
            print(f"总结果数: {result.total_num}")
            print(f"消息: {result.message}")
            
            if result.list:
                print(f"\nMV列表:")
                for i, mv in enumerate(result.list, 1):
                    print(f"  {i}. {mv.mv_title} - {mv.singer_name}")
                    print(f"     ID: {mv.mv_id}, 时长: {mv.duration}秒")
                    print(f"     播放次数: {mv.play_count}")
                    if mv.publish_date:
                        print(f"     发布日期: {mv.publish_date}")
            
            if result.zhida and result.zhida.title:
                print(f"\n直达结果: {result.zhida.title} - {result.zhida.sub_title}")
                
        except Exception as e:
            print(f"搜索失败: {e}")


async def test_radio_search():
    print("\n" + "="*80)
    print("测试电台搜索能力")
    print("="*80)
    
    tool = QQMusicRadioSearchTool()
    
    test_cases = [
    ("故事", 1, 3),
    ("音乐", 1, 2),
    ("情感", 1, 3),
    ]
    
    for query, page, num in test_cases:
        print(f"\n搜索: {query} (页码={page}, 数量={num})")
        try:
            result = await tool._arun(query=query, page=page, num=num)
            print(f"状态: {result.status}")
            print(f"关键词: {result.keyword}")
            print(f"当前页: {result.cur_page}")
            print(f"当前返回数: {result.cur_num}")
            print(f"总结果数: {result.total_num}")
            print(f"消息: {result.message}")
            
            if result.list:
                print(f"\n电台节目列表:")
                for i, radio in enumerate(result.list, 1):
                    print(f"  {i}. {radio.program_name} - {radio.singer_name}")
                    print(f"     ID: {radio.program_id}, 时长: {radio.duration}秒")
                    print(f"     收听次数: {radio.listen_count}")
            
            if result.zhida and result.zhida.title:
                print(f"\n直达结果: {result.zhida.title} - {result.zhida.sub_title}")
                
        except Exception as e:
            print(f"搜索失败: {e}")


async def test_pagination():
    print("\n" + "="*80)
    print("测试分页功能")
    print("="*80)
    
    tool = QQMusicSongSearchTool()
    query = "周杰伦"
    
    print(f"\n搜索: {query}，测试分页")
    for page in range(1, 4):
        print(f"\n第 {page} 页:")
        try:
            result = await tool._arun(query=query, page=page, num=5)
            print(f"当前页: {result.cur_page}, 返回数: {result.cur_num}, 总数: {result.total_num}")
            
            if result.list:
                for i, song in enumerate(result.list, 1):
                    print(f"  {(page-1)*5 + i}. {song.song_name} - {song.singer_name}")
            
            if not result.list:
                print("  无更多结果")
                break
                
        except Exception as e:
            print(f"搜索失败: {e}")
            break


async def test_edge_cases():
    print("\n" + "="*80)
    print("测试边界情况")
    print("="*80)
    
    tool = QQMusicSongSearchTool()
    
    edge_cases = [
    ("", 1, 5, "空关键词"),
    ("a", 1, 5, "过短关键词"),
    ("周杰伦", 6, 10, "超出最大页码"),
    ("周杰伦", 1, 60, "超出最大数量"),
    ("周杰伦", 0, 5, "页码为0"),
    ("周杰伦", 1, 0, "数量为0"),
    ]
    
    for query, page, num, description in edge_cases:
        print(f"\n测试: {description} (query='{query}', page={page}, num={num})")
        try:
            result = await tool._arun(query=query, page=page, num=num)
            print(f"状态: {result.status}")
            print(f"消息: {result.message}")
            if result.error_msg:
                print(f"错误信息: {result.error_msg}")
            
        except Exception as e:
            print(f"异常: {e}")


async def test_special_characters():
    print("\n" + "="*80)
    print("测试特殊字符")
    print("="*80)
    
    tool = QQMusicSongSearchTool()
    
    special_cases = [
    ("周杰伦;告白气球", 1, 3, "包含分号"),
    ("周杰伦&林俊杰", 1, 3, "包含&符号"),
    ("周杰伦(最伟大的作品)", 1, 3, "包含括号"),
    ("周杰伦's song", 1, 3, "包含英文单引号"),
    ("周杰伦-告白气球", 1, 3, "包含连字符"),
    ]
    
    for query, page, num, description in special_cases:
        print(f"\n测试: {description}")
        print(f"搜索: {query}")
        try:
            result = await tool._arun(query=query, page=page, num=num)
            print(f"状态: {result.status}")
            print(f"消息: {result.message}")
            
            if result.list:
                print(f"找到 {len(result.list)} 个结果")
                for i, song in enumerate(result.list[:2], 1):
                    print(f"  {i}. {song.song_name} - {song.singer_name}")
            
        except Exception as e:
            print(f"异常: {e}")


async def test_all_abilities():
    print("\n" + "="*80)
    print("综合测试所有原子能力")
    print("="*80)
    
    query = "周杰伦"
    
    abilities = [
    ("歌曲搜索", QQMusicSongSearchTool()),
    ("歌单搜索", QQMusicPlaylistSearchTool()),
    ("专辑搜索", QQMusicAlbumSearchTool()),
    ("MV搜索", QQMusicMVSearchTool()),
    ]
    
    for ability_name, tool in abilities:
        print(f"\n{ability_name}: {query}")
        try:
            result = await tool._arun(query=query, page=1, num=3)
            print(f"状态: {result.status}")
            print(f"消息: {result.message}")
            
            if result.list:
                print(f"找到 {len(result.list)} 个结果")
            
        except Exception as e:
            print(f"异常: {e}")


async def main():
    print("\n" + "="*80)
    print("QQ音乐搜索工具测试套件")
    print("="*80)
    
    # await test_song_search()
    # await test_playlist_search()
    # await test_album_search()
    # await test_mv_search()
    # await test_radio_search()
    # await test_pagination()
    # await test_edge_cases()
    # await test_special_characters()
    await test_all_abilities()
    
    print("\n" + "="*80)
    print("测试完成")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
