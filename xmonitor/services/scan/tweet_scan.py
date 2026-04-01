import datetime
import random
import re
import time


def scan_page_content(page, url, blocked_list, deps):
    history_ids = deps.history_ids
    log_to_ui = deps.log_to_ui
    reorder_articles_for_scan = deps.reorder_articles_for_scan
    should_skip_content_by_policy = deps.should_skip_content_by_policy
    get_effective_delegated_account = deps.get_effective_delegated_account
    """
    优化版本的推文评论抓取
    - 增量处理articles，避免重复处理
    - 改进滚动和加载检测
    - 简化并稳定整体流程
    """
    results = []
    seen_in_page = set()
    processed_article_hashes = set()  # 记录已处理的article

    try:
        tweet_id_match = re.search(r'status/(\d+)', url)
        if not tweet_id_match:
            return [], "链接无效"

        main_tweet_id = tweet_id_match.group(1)
        log_to_ui("info", f"🎯 开始扫描推文: {main_tweet_id}")

        # 详细日志：准备访问页面
        log_to_ui("debug", f"🐛 [DEBUG] 准备执行 page.get(\"{url}\")")

        # 访问页面
        page.get(url)
        log_to_ui("debug", f"🐛 [DEBUG] page.get() 返回，当前URL: {page.url}")

        log_to_ui("info", f"⏳ 等待页面加载...")

        # 详细日志：等待元素加载
        try:
            page.wait.ele_displayed('tag:article', timeout=15)
            log_to_ui("debug", f"🐛 [DEBUG] tag:article 元素已显示")
        except Exception as wait_err:
            log_to_ui("error", f"❌ 等待页面加载超时或失败: {wait_err}")
            log_to_ui("debug", f"🐛 [DEBUG] 当前页面HTML前500字符: {page.html[:500]}")
            raise wait_err

        log_to_ui("success", f"✅ 页面已加载")
        time.sleep(2)

        # 配置参数
        max_scrolls = 50
        max_consecutive_empty = 8
        scroll_step = 800

        scroll_count = 0
        consecutive_empty = 0
        total_captured = 0
        total_processed = 0
        debug_skipped = {
            "no_user": 0,
            "no_handle": 0,
            "no_content": 0,
            "blacklist": 0,
            "duplicate": 0,
            "has_reply": 0,
            "emoji_only": 0,
            "blocked_mention": 0,
        }

        initial_articles = page.eles('tag:article')
        log_to_ui("info", f"📊 初始发现 {len(initial_articles)} 个article")

        while scroll_count < max_scrolls:
            scroll_count += 1

            # 检查URL
            if url not in page.url:
                log_to_ui("error", f"❌ 页面跳转，返回原页面...")
                page.get(url)
                time.sleep(2)

            # 获取当前所有articles
            try:
                articles = page.eles('tag:article', timeout=1)
            except Exception as e:
                log_to_ui("debug", f"获取articles失败: {e}")
                articles = []

            articles = reorder_articles_for_scan(articles)

            # 处理新的articles
            new_count = 0
            for article in articles:
                try:
                    if random.random() < 0.18:
                        time.sleep(random.uniform(0.02, 0.12))
                    article_html = article.html
                    article_hash = hash(article_html[:300])

                    # 跳过已处理过的article
                    if article_hash in processed_article_hashes:
                        continue

                    processed_article_hashes.add(article_hash)
                    new_count += 1
                    total_processed += 1

                    # 跳过原推文
                    if f'/status/{main_tweet_id}' in article_html and '<time' in article_html:
                        continue

                    # 提取handle
                    user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0.01)
                    if not user_ele:
                        debug_skipped["no_user"] += 1
                        continue

                    handle_match = re.search(r'(@[\w_]+)', user_ele.text)
                    if not handle_match:
                        debug_skipped["no_handle"] += 1
                        continue
                    handle = handle_match.group(1)

                    # 过滤保护名单
                    if handle in blocked_list:
                        debug_skipped["blacklist"] += 1
                        continue

                    # 提取内容
                    text_ele = article.ele('css:[data-testid="tweetText"]', timeout=0.01)
                    content = text_ele.text.replace('\n', ' ').strip() if text_ele else ""

                    # 详细日志：打印提取到的原始内容，帮助调试
                    log_to_ui("debug", f"🔍 [DEBUG] Handle: {handle}, tweetText: '{content}', Raw: '{article.text[:50].replace(chr(10), ' ')}...'")

                    if not content:
                        debug_skipped["no_content"] += 1
                        continue
                    should_skip_policy, skip_reason = should_skip_content_by_policy(content)
                    if should_skip_policy:
                        if skip_reason == "emoji_only":
                            debug_skipped["emoji_only"] += 1
                        elif skip_reason == "blocked_mention":
                            debug_skipped["blocked_mention"] += 1
                        continue

                    # 去重
                    unique_key = f"{handle}_{content[:50]}"
                    if unique_key in seen_in_page or unique_key in history_ids:
                        debug_skipped["duplicate"] += 1
                        continue
                    seen_in_page.add(unique_key)

                    # 检查是否有回复
                    reply_btn = article.ele('css:[data-testid="reply"]', timeout=0.01)
                    has_reply = False
                    if reply_btn:
                        aria_label = (reply_btn.attr("aria-label") or "").lower()
                        reply_text = reply_btn.text.strip()
                        if re.search(r'(\d+)', aria_label):
                            match_num = re.search(r'(\d+)', aria_label)
                            if match_num and int(match_num.group(1)) > 0:
                                has_reply = True
                        elif reply_text.isdigit() and int(reply_text) > 0:
                            has_reply = True
                        elif 'k' in reply_text.lower() or 'm' in reply_text.lower():
                            has_reply = True

                    if has_reply:
                        debug_skipped["has_reply"] += 1
                        continue

                    # 捕获成功
                    total_captured += 1
                    log_to_ui("success", f"✅ 捕获 [{total_captured}]: {handle} 内容: {content[:30]}...")
                    results.append({
                        "handle": handle,
                        "content": content,
                        "key": unique_key,
                        "source": url,
                        "time": datetime.datetime.now().strftime("%H:%M:%S")
                    })

                except Exception as article_err:
                    log_to_ui("debug", f"处理article异常: {article_err}")
                    continue

            # 判断是否有新内容
            if new_count == 0:
                consecutive_empty += 1
                log_to_ui("info", f"⏳ 无新内容 ({consecutive_empty}/{max_consecutive_empty})")
                if consecutive_empty >= max_consecutive_empty:
                    log_to_ui("info", "🏁 扫描结束")
                    break
            else:
                consecutive_empty = 0
                log_to_ui("info", f"📝 第{scroll_count}次: {len(articles)} 个articles，新增 {new_count} 个")

            # 检查并点击"显示可能的垃圾信息"按钮
            try:
                # 查找所有可能的按钮和可点击元素
                all_elements = []
                try:
                    all_elements.extend(page.eles('tag:button', timeout=0.3))
                except:
                    pass
                try:
                    all_elements.extend(page.eles('tag:span', timeout=0.3))
                except:
                    pass
                try:
                    all_elements.extend(page.eles('tag:div[role="button"]', timeout=0.3))
                except:
                    pass

                for element in all_elements:
                    try:
                        element_text = (element.text or "").strip()

                        # 检测关键词（中英文）
                        spam_keywords = [
                            '显示可能的垃圾信息',
                            '显示更多回复',
                            '显示其他回复',
                            'Show additional replies',
                            'Show more replies',
                            'Show hidden replies'
                        ]

                        # 如果文本包含关键词，点击它
                        if any(keyword in element_text for keyword in spam_keywords):
                            if element.states.is_displayed:
                                log_to_ui("info", f"🔓 发现隐藏回复按钮: {element_text[:50]}")
                                page.run_js('arguments[0].click()', element)
                                time.sleep(2)  # 等待内容加载
                                log_to_ui("success", f"✅ 已展开隐藏的回复，继续扫描...")
                                # 展开后不break，继续检查是否还有其他按钮
                    except:
                        continue
            except:
                pass

            # 滚动
            try:
                prev_top = page.run_js('return window.scrollY || document.documentElement.scrollTop')
                page.run_js(f'window.scrollBy(0, {scroll_step}); void(0);')
                time.sleep(random.uniform(0.7, 1.0))
                new_top = page.run_js('return window.scrollY || document.documentElement.scrollTop')

                if new_top > prev_top:
                    log_to_ui("info", f"📜 滚动 {new_top - prev_top}px")
                else:
                    consecutive_empty += 1
                    log_to_ui("info", f"⏳ 无法滚动")
                    if consecutive_empty >= max_consecutive_empty:
                        break
            except Exception as scroll_err:
                log_to_ui("debug", f"滚动异常: {scroll_err}")
                consecutive_empty += 1

            # 进度
            if scroll_count % 10 == 0:
                log_to_ui("info", f"📊 进度: {scroll_count}/{max_scrolls}，捕获 {total_captured} 条")

        # 统计
        log_to_ui("info", f"📊 统计: 处理 {total_processed} 个articles")
        log_to_ui("info", f"   跳过: 无user({debug_skipped['no_user']}), 无handle({debug_skipped['no_handle']}), 无内容({debug_skipped['no_content']})")
        log_to_ui("info", f"   跳过: 保护名单({debug_skipped['blacklist']}), 重复({debug_skipped['duplicate']}), 有回复({debug_skipped['has_reply']})")
        log_to_ui("info", f"   跳过: 纯表情({debug_skipped['emoji_only']}), 指定@过滤({debug_skipped['blocked_mention']})")
        log_to_ui("success", f"✨ 扫描完成: 捕获 {len(results)} 条评论")

    except Exception as e:
        log_to_ui("error", f"扫描异常: {str(e)}")
        return [], str(e)

    return results, None
