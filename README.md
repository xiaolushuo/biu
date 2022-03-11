## biu

一只正在成长的小爬虫

现支持参数如下：

```shell
optional arguments:
  -h, --help            show this help message and exit
  --target TARGET       crawler target site
  --slow_mo SLOW_MO     Crawl speed,The unit is milliseconds
  --headless HEADLESS   Whether to display the browser interface
  --devtools DEVTOOLS   Whether to enable development and debugging
  --login LOGIN         import login script path,E.g --login oa_login.py
  --chrome_path CHROME_PATH   configure the chrome path
  --proxy PROXY         Network proxy mode,E.g http://127.0.0.1:8089 or socks5://127.0.0.1:10808
  --trace TRACE         Track the crawling process for replay,E.g trace_test.zip
  --out_xls OUT_XLS     result to output .xls
```

特点：

1. 支持将登录模块单独存储为脚本；

2. 可对爬虫的过程进行可视化回放；
