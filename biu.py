
from importlib.resources import contents
import traceback
from turtle import pen
from playwright.sync_api import sync_playwright
from urllib import parse
import re
import os
import json
import hashlib
import redis
from urllib.parse import unquote
import xlwt
from queue import Queue
from urllib.parse import urlparse
import tldextract
import logging
import platform
import argparse
import sys
import logging
from tempfile import NamedTemporaryFile
import os
import importlib

logging.basicConfig(format='%(asctime)s.%(msecs)03d %(message)s',
                    datefmt='[biu~] %Y-%m-%d %H:%M:%S')

logging.getLogger().setLevel(logging.DEBUG)
logger = logging.getLogger()


def initBrowser(browserType="chromium", browserConfig={"headless": False}):
    curBrowserType = None
    if browserType:
        browserType = browserType.lower()
    # with sync_playwright() as p:
    # p = sync_playwright()
    p = sync_playwright().start()
    # 多次调用，会：
    # 发生异常: Error
    # It looks like you are using Playwright Sync API inside the asyncio loop.
    # Please use the Async API instead.

    if browserType == "chromium":
        curBrowserType = p.chromium
    elif browserType == "firefox":
        curBrowserType = p.firefox
    elif browserType == "webkit":
        curBrowserType = p.webkit
    # print("curBrowserType\t=\t%s" % curBrowserType)
    # print("browser_path\t=\t%s" % curBrowserType.executable_path,
    #       type(curBrowserType.executable_path))
    # curBrowserType=<BrowserType name=chromium executable_path=/Users/limao/Library/Caches/ms-playwright/chromium-901522/chrome-mac/Chromium.app/Contents/MacOS/Chromium>

    if not curBrowserType:
        #print("Unsupported playwright browser type: %s" % browserType)
        return None

    # browser = curBrowserType.launch(headless=False)
    # browser = curBrowserType.launch(**browserLaunchOptionDict)
    browser = curBrowserType.launch(**browserConfig)
    #print("browser=%s" % browser)
    # browser=<Browser type=<BrowserType name=chromium executable_path=/Users/limao/Library/Caches/ms-playwright/chromium-901522/chrome-mac/Chromium.app/Contents/MacOS/Chromium> version=93.0.4576.0>

    return browser


def handle_dialog(dialog):
    #print("93", dialog.message)
    dialog.dismiss()


# def test_css():
#     #print("add_style_tag")
#     page.add_style_tag(content=".focusClass {border:10px solid #FE0000;}")
#     page.add_script_tag(content='<script>console.log("111111111111111111111111")</script>')


def initPage(pageConfig=None, browser=None):
    if not browser:
        browser = initBrowser()
    # 创建隐身窗口
    context = browser.new_context(
        http_credentials={"username": "admin", "password": "Redhat@2015"})
    context.tracing.start(screenshots=True, snapshots=True)
    page = context.new_page()
    page.add_style_tag(content=".focusClass {border:10px solid #FE0000;}")
    # page.add_init_script(path="./dom_monitoring.js")

    # page.on("dialog", handle_dialog)
    # page.expose_function("getlink", getlink)
    # page.expose_function("test_css", test_css)

    if pageConfig:
        if "pageLoadTimeout" in pageConfig:
            curPageLoadTimeout = pageConfig["pageLoadTimeout"]
            curPageLoadTimeoutMilliSec = curPageLoadTimeout * 1000
            page.set_default_navigation_timeout(curPageLoadTimeoutMilliSec)
            page.set_default_timeout(curPageLoadTimeoutMilliSec)
    return page, context


def closeBrowser(browser):
    browser.close()


def firstOpen(target):
    page = initPage(browser=browser)
    page.goto(target, wait_until="networkidle", timeout=600000)

# def tagFocus(page):
#     page.evaluate('''() => {
#    function focusInput() {
#     console.log("注入了tagFocus js脚本")
#     var elements = document.querySelectorAll("input,span,a,link,select,textarea");
#     console.log(elements);
#     for (var i=0; i < elements.length; i++) {
#         elements[i].onfocus = function() { this.className = 'focusClass'; };
#         elements[i].onblur = function() { this.className = ''; };
#     }
#   }
#   setTimeout(function() {
#     focusInput()
# }, 100);
#     }''')


class crawlTar:
    def __init__(self, page, tarurl):
        self.page = page
        self.target = tarurl
        self.js_content_list = []  # 对已经触发过的tag打标，防止重复点击
        self.req_list = []  # 已经请求过的链接，重复的请求不再收集
        self.url_list = []  # 忘了
        self.q = Queue(maxsize=0)  # 任务队列
        self.wbk = xlwt.Workbook()  # 初始化workbook对象
        self.sheet = self.wbk.add_sheet('My_Worksheet')  # 创建表
        self.sheet.write(0, 0, "链接")
        self.sheet.write(0, 1, "请求方式")
        self.sheet.write(0, 2, "headers头")
        self.sheet.write(0, 3, "data数据")
        self.page.on("request", lambda request: self.handle_request(request))
        # self.page.on("console", lambda msg: self.echo_console(msg))
        self.page.on("dialog", lambda dialog: dialog.accept())
    # 标注链接及来源
    n = 0
    def getlink(self, link, source):
        # #print("【修复前】获取到的链接为:\t", link, "\t", source)
        new_url = self.repair_url(link)
        # #print("【修复后】获取到的链接为:\t", new_url, "\t", source)
        tarurl_domain = urlparse(self.target).netloc
        url_domain = urlparse(new_url).netloc
        # #print(tarurl_domain, url_domain)
        # 如果是同域的
        if tarurl_domain == url_domain:
            if self.parse_link_static(new_url):
                pass
            else:
                getlinkdict = {}
                getlinkdict["url"] = new_url
                getlinkdict["source"] = source
                # #print(getlinkdict, "\tvvvvvsssss\t", self.url_list)
                if new_url in self.url_list:
                    pass
                else:
                    #print("【同域】:\t", new_url, "\t", source)
                    self.url_list.append(new_url)
                    logger.info("request\t>>>\t{}".format(new_url))
                    self.q.put(new_url)

    def echo_console(self, msg):
        if "Error" in msg.text or "Failed" in msg.text:
            pass
        else:
            print("console info:\t", msg.text)

    def handle_request(self, request):
        req_data = {}
        # print(request.url)
        # #print("handle_request:\t", request.url, request.method)
        # #print("当前请求:\t", request.url, "\tvs\t", "网页输入栏:\t", self.page.url)
        if request.is_navigation_request() and not self.page.frames[0].parent_frame:
            # self.page.route(request.url,lambda route: route.fulfill(
            #     status=204
            # ))
            # print("handle_navigation:\t", request.url)
            self.getlink(request.url, "handle_navigation")
        else:
            self.getlink(request.url, "handle_request")
            # if is_target(request.url, tarurl):
            #     if parse_link_static(request.url) == False:
            #         n = n + 1
            #         sheet.write(n, 0, request.url)
            #         sheet.write(n, 1, request.method)
            #         sheet.write(n, 2, json.dumps(request.headers))
            #         sheet.write(n, 3, json.dumps(request.post_data))
            #         q.put(request.url)
        req_data["url"] = request.url
        req_data["method"] = request.method
        req_data["headers"] = request.headers
        if request.post_data:
            req_data["body_data"] = request.post_data
        else:
            req_data["body_data"] = ""
        # 最后将结果写入excle
        for i in self.req_list:
            if request.url == i["url"] and request.method == i["method"]:
                pass
            
        if self.set_req_list(request):
            # print(request.url,"\n",req_data,"\n",self.req_list)
            self.req_list.append(req_data)

    def set_req_list(self,request):
        for i in self.req_list:
            if request.url == i["url"] and request.method == i["method"]:
                return False
        return True
    def test_css(self):
        #print("add_style_tag")
        self.page.add_style_tag(
            content=".focusClass {border:2px solid #FF0400;outline:none}")
        self.page.add_script_tag(
            content='console.log("111111111111111111111111")')

    def repair_url(self, url):
        tarurl_domain = urlparse(self.target).netloc
        tarurl_scheme = urlparse(self.target).scheme
        url_domain = urlparse(url).netloc
        # 判断是否为完整链接
        new_url = ""
        if "http://" in url or "https://" in url:
            return url
        else:
            new_url = tarurl_scheme + "://" + tarurl_domain + url
        return new_url

    def listening_event(self):
        self.page.evaluate('''() => {
        function interceptClickEvent(e) {
        var href;
        var target = e.target || e.srcElement;
        if (target.tagName === 'A') {
            href = target.href;
            console.log(href);
            e.preventDefault();
        }
    }

    document.body.addEventListener('click', interceptClickEvent);

    const unchange = {"writable": false, "configurable": false};
    //hook History API
    window.history.pushState = function(a, b, url) { window.getlink(url,"history")}
    Object.defineProperty(window.history,"pushState",unchange);
    window.history.replaceState = function(a, b, url) { window.getlink(url,"history")}
    Object.defineProperty(window.history,"replaceState",unchange);
    //hook new window
    window.open = function (url) { window.getlink(url,"open")}
    Object.defineProperty(window,"open",unchange);
    //hook close window
    window.close = function() {console.log("trying to close page.");};
    Object.defineProperty(window,"close",unchange);
    //hook hash change route
    window.addEventListener("hashchange", function () {
        window.getlink(document.location.href,"hashchange")
        console.log("#hashchange#",document.location.href);
    });
    // hook new requests
    let oldWebSocket = window.WebSocket;
    window.WebSocket = function (url) {
        window.getlink(url,"WebSocket")
        console.log(`WebSocket: ${url}`);
        return new oldWebSocket(url);
    };

    let oldEventSource = window.EventSource;
    window.EventSource = function (url) {
        window.getlink(url,"EventSource")
        console.log(`EventSource: ${url}`);
        return new oldEventSource(url);
    };

    let oldFetch = window.fetch;
    window.fetch = function (url) {
        window.getlink(url,"fetch")
        console.log(`fetch: ${url}`);
        return oldFetch(url);
    };
    // hook form reset
    HTMLFormElement.prototype.reset = function () {
    console.log("cancel reset form")
    };
    Object.defineProperty(HTMLFormElement.prototype, "reset", unchange);
    // hook time func
    let oldSetTimeout = window.setTimeout;
    window.setTimeout = function (time) {
        //console.log(`setInterval: ${time}`);
        return oldSetTimeout(1.5);
    };

    let oldSetInterval = window.setInterval;
    window.setInterval = function (time) {
        //console.log(`setInterval: ${time}`);
        return oldSetInterval(1.5);
    };
    }
    ''')

    def listening_dom(self):
        self.page.evaluate('''() => {
        let xy_dict = {};
        //dom monitor
        console.log("开始监听dom")
function findnodeclass(data) {
  if (data.className) {
    let nodeclass = data.className;
    if (nodeclass == "available") {
      return true;
    }
  } else {
    return findnodeclass(data.parentNode);
  }
  return false;
}

let findId = (function (findNode) {
  return function fn(data) {
    if (data.children && data.children.length) {
      for (let f = 0; f < data.children.length; f++) {
        // console.log(data.children[f].tagName);
        if (data.children[f].tagName == "SPAN") {
          if (findnodeclass(data.children[f])) {
            findNode = data.children[f];
            //console.log("28", findNode);
            return findNode;
          }
        }
        if ((findNode = fn(data.children[f]))) break;
      }
      return findNode;
    }
  };
})(null);

let find_ul_span = (function (findNode) {
  return function fn(data) {
    if (data.children && data.children.length) {
      for (let f = 0; f < data.children.length; f++) {
        // console.log(data.children[f].tagName);
        if (data.children[f].tagName == "SPAN") {
          findNode = data.children[f];
          // console.log("28", findNode);
          return findNode;
        }
        if ((findNode = fn(data.children[f]))) break;
      }
      return findNode;
    }
  };
})(null);

let findtable = (function (findNode) {
  let table_list = [];
  return function fn(data) {
    if (data.children && data.children.length) {
      for (let f = 0; f < data.children.length; f++) {
        //console.log(data.children[f].tagName);
        if (data.children[f].tagName == "TABLE") {
          findNode = data.children[f];
          if (table_list.indexOf(findNode) != -1) {
            continue;
          } else {
            // console.log("获取到table的节点>>>", findNode);
            table_list.push(findNode);
            break;
          }
        } else fn(data.children[f]);
      }
      // console.log("50", table_list);
      return table_list;
    }
  };
})(null);

let findul = (function (findNode) {
  let ul_list = [];
  return function fn(data) {
    if (data.children && data.children.length) {
      for (let f = 0; f < data.children.length; f++) {
        // console.log(data.children[f].tagName);
        if (data.children[f].tagName == "UL") {
          findNode = data.children[f];
          // console.log("72", findNode);
          if (ul_list.indexOf(findNode) != -1) {
            continue;
          } else {
            // console.log("获取到Ul的节点>>>", findNode);
            ul_list.push(findNode);
            break;
          }
        } else fn(data.children[f]);
      }
      // console.log("50", table_list);
      return ul_list;
    }
  };
})(null);

//dom monitor
var observer = new MutationObserver(function (mutations) {
  let dom_list = [];
  // console.log('eventLoop	nodesMutated:',	mutations.length);
  mutations.forEach(function (mutation) {
    //console.log("dom改变的类型>>>",mutation.type)
    if (mutation.type === "childList") {
      for (let i = 0; i < mutation.addedNodes.length; i++) {
        let addedNode = mutation.addedNodes[i];
        if (dom_list.indexOf(addedNode) != -1) {
          continue;
        } else {
          dom_list.push(addedNode);
          // console.log("新增dom内容为: ", addedNode);
          //自动选择下拉框
          let ulNode = findul(addedNode);
          // console.log("102", ulNode);
          if (ulNode) {
            for (let i = 0; i < ulNode.length; ++i) {
              let ulul = find_ul_span(ulNode[i]);
              if (ulul) {
                // console.log("105", ulul);
                ulul.click();
              }
            }
          }
          // 自动点击时间选择器
          let tableNode = findtable(addedNode);
          if (tableNode) {
            for (let i = 0; i < tableNode.length; ++i) {
              let ss = findId(tableNode[i]);
              //console.log("126",ss);
              if (ss) {
                console.log("71", ss);
                //ss.click();
                setTimeout(function () {
                  ss.click();
                }, 1000);
              }
            }
          }
        }
      }
    } else if (mutation.type === "attributes") {
      // 某节点的一个属性值被更改
      let element = mutation.target;
      var element_val = element.getAttribute(mutation.attributeName);
      // console.log(mutation.attributeName, "->", element_val);
      var change_dom = mutation.target.parentNode;
      var change_dom_tagname = mutation.target.parentNode.tagName;
        // console.log(change_dom_tagname,change_dom)
        // if (change_dom && change_dom_tagname == "DIV") {
        //   // console.log("对应更改的DOM>>>>", change_dom);
        //   let ulNode = findul(change_dom);
        //   if (ulNode) {
        //     for (let i = 0; i < ulNode.length; ++i) {
        //       let ulul = find_ul_span(ulNode[i]);
        //       if (ulul) {
        //         ulul.click();
        //       }
        //     }
        //   }
        // }
    }
  });
});
observer.observe(window.document.documentElement, {
  childList: true,
  attributes: true,
  characterData: false,
  subtree: true,
  characterDataOldValue: false,
});



        //node list
        //
        var treeWalker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_ELEMENT,
        {
            acceptNode: function (node) {
            return NodeFilter.FILTER_ACCEPT;
            },
        }
        );
        while (treeWalker.nextNode()) {
        var element = treeWalker.currentNode;
        let xy_list = []
        for (k = 0; k < element.attributes.length; k++) {
            //console.log("338",element);
            //console.log("339",element.tagName);
            attr = element.attributes[k];
            //console.log("341",attr);
            //console.log("342",attr.nodeName);
            if (attr.nodeName.startsWith("on")) {
            let eventName = attr.nodeName.replace("on", "");
            let dict_xy = {};
            var X1 =
                element.getBoundingClientRect().left +
                document.documentElement.scrollLeft;

            var Y1 =
                element.getBoundingClientRect().top +
                document.documentElement.scrollLeft;
            dict_xy["x"] = X1;
            dict_xy["y"] = Y1;
            dict_xy["event"] = eventName;
            //console.log("559。。。。。。。。。。。。",dict_xy);
            xy_list.push(dict_xy);
            if (element.tagName == "TR") {
                let arr = element.querySelectorAll("td");
                for (let i = 0; i < arr.length; ++i) {
                let dict_xy = {};
                //console.log(arr[i]);
                let X =
                    arr[i].getBoundingClientRect().left +
                    arr[i].getBoundingClientRect().width / 2 +
                    document.documentElement.scrollLeft;
                let Y =
                    arr[i].getBoundingClientRect().top +
                    arr[i].getBoundingClientRect().height / 2 +
                    document.documentElement.scrollLeft;
                console.log("x: " + X, "y: " + Y);
                dict_xy["x"] = X;
                dict_xy["y"] = Y;
                dict_xy["event"] = eventName;
                xy_list.push(dict_xy);
                }
            }
            xy_dict["data"] = xy_list
            }
        }
        }
        //console.log("xy_dict",xy_dict);
            }
            ''')

    def find_a(self):
        # 获取A标签的完整链接
        #print("开始探测A标签...")
        self.page.evaluate('''() => {
            console.log("开始获取A标签.....")
            // 不点击a标签的情况下，获取完整href链接，调用方式为getAbsoluteUrl(链接)
            var getAbsoluteUrl = (function() {
            var a;
            return function(url) {
                if(!a) a = document.createElement('a');
                a.href = url;
                return a.href;
            };})();

            function getSrcAndHrefLinks(nodes) {

            for(let node of nodes){
                //console.log(node);
                let src = node.getAttribute("src");
                let href = node.getAttribute("href");
                let action = node.getAttribute("action");
                if (src){
                    //console.log(src);
                    window.getlink(getAbsoluteUrl(src),"src");
                    console.log("262",getAbsoluteUrl(src));
                }
                if (href){
                    console.log("412###########",href);
                    window.getlink(getAbsoluteUrl(href),"href");
                    if (href.startsWith("javascript")){
                        console.log("417",href,getAbsoluteUrl(href))
                        eval(href.substring(11))
                    }
                    console.log("414",getAbsoluteUrl(href));
                }
                if(action){
                    window.getlink(getAbsoluteUrl(action),"action");
                    console.log(getAbsoluteUrl(action));
                }
            }
        }
            getSrcAndHrefLinks(document.querySelectorAll("[src],[href],[action]"))
            // 监听click事件与mousedown事件
            function interceptClickEvent(e) {
        var href;
        var target = e.target || e.srcElement;
        if (target.tagName === 'A') {
            href = target.href;
            window.getlink(href,"interceptClickEvent");
            console.log(href);
            // 这里延迟是因为与window.open 冲突了
            setTimeout(function(){e.preventDefault()},1000);
            //e.preventDefault();
        };
    };
    document.body.addEventListener('click', interceptClickEvent);
    document.body.addEventListener('mousedown', interceptClickEvent);

        }
        ''')

    def input_list(self):
        #print("开启探测input....")
        inputs = self.page.query_selector_all("input")
        n = 0
        for i in inputs:
            # 获取父节点,判断input的父节点是否为form
            try:
                tagName = i.get_property("parentNode").evaluate(
                    "node => node.tagName")
                if tagName == "FORM":
                    self.get_form_script()
                    continue
                else:
                    n = n + 1
                    #print(i.evaluate("node => node.outerHTML"))
                    # 获取placeholder的值
                    placeholder_v = i.get_attribute("placeholder")
                    i_type = i.get_attribute("type")
                    #print("input_type:\t", i_type)
                    if i_type == "radio":
                        if self.marktag(i, "radio"):
                            # name = i.get_attribute("name")
                            try:
                                value = i.get_attribute("value")
                                self.page.select_option(
                                    "#"+name, value, timeout=0)
                            except:
                                pass
                    elif i_type == "text":
                        #print("发现text input")
                        input_node = i.evaluate("node => node.outerHTML")
                        # print("input_outerHTML", i.evaluate(
                        #     "node => node.outerHTML"))
                        if self.marktag(input_node, "input_text"):
                            name_v = i.get_attribute("name")
                            readonly_v = i.get_attribute("readonly")
                            value_v = i.get_attribute("value")

                            #print("判断是否可编辑...")
                            # self.page.pause()
                            if readonly_v and placeholder_v:
                                self.page.click(
                                    "[placeholder=\"{}\"]".format(placeholder_v))

                            elif placeholder_v:
                                #print("获取input_placeholder")
                                self.page.click(
                                    "[placeholder=\"{}\"]".format(placeholder_v))
                                self.page.fill("[placeholder=\"{}\"]".format(
                                    placeholder_v), "test")
                            elif name_v:
                                #print("获取input_name")
                                self.page.click("[name=\"{}\"]".format(name_v))
                                self.page.fill("[name=\"{}\"]".format(
                                    name_v), "test")
                            elif value_v:
                                try:
                                    self.page.fill("#"+name, "test")
                                except Exception as e:
                                    traceback.print_exc()
                                    #print("报错了:", e)

                    elif i_type == "hidden":
                        inputs = self.page.query_selector_all("input")
                        #print("发现隐藏input")
                        i.evaluate("node => node.value='test'")
                    elif i_type == "password":
                        password_node = i.evaluate("node => node.outerHTML")
                        if self.marktag(password_node, "input_text"):
                            # 获取placeholder的值
                            placeholder_v = i.get_attribute("placeholder")
                            if placeholder_v != None:
                                #print("获取input_placeholder")
                                self.page.click(
                                    "[placeholder=\"{}\"]".format(placeholder_v))
                                self.page.fill("[placeholder=\"{}\"]".format(
                                    placeholder_v), "test")
                            name_v = i.get_attribute("name")
                            #print("622", name_v)
                            if name_v != None:
                                #print("获取input_name")
                                self.page.click("[name=\"{}\"]".format(name_v))
                                self.page.fill("[name=\"{}\"]".format(
                                    name_v), "test")
                            value_v = i.get_attribute("value")
                            if value_v != None:
                                try:
                                    self.page.fill("#"+name, "test")
                                except Exception as e:
                                    traceback.print_exc()
                                    #print("报错了:", e)
                    elif i_type == "submit":
                        #print("发现submit input")
                        input_node = i.evaluate("node => node.outerHTML")
                        #print("提交input表单....")
                        if self.marktag(input_node, "input_submit"):
                            i.click()
                    elif placeholder_v:
                        self.page.click(
                            "[placeholder=\"{}\"]".format(placeholder_v))
            except:
                pass

    def all_a_click(self):
        #print("点击所有包含javascript的标签...")
        # 获取链接的标签
        link_attrs = "[src],[href],[action],[data-url],[longDesc],[lowsrc]"
        nodes = self.page.query_selector_all(link_attrs)
        # print (nodes)
        for node in nodes:
            # #print(node)
            for attr in link_attrs.split(","):
                link = node.get_attribute(
                    attr.replace('[', '').replace(']', ''))
                if not link:
                    # #print("1",link)
                    pass
                elif self.parse_link_static(link):
                    pass
                else:
                    # #print("2",link)
                    try:
                        if "javascript" in link:
                            #print(link)
                            node.click()
                    except Exception as e:
                        traceback.print_exc()

    # 获取form表单

    def get_form_script(self):
        #print("开启探测form....")
        # 返回值需要是一个可序列化的值，不然返回值为none
        form_data = self.page.evaluate('''() => {
        let formdicts = {};
        let formItem_list =[]
        for (let i = 0; i < document.forms.length; i++) {
            form = document.forms[i];
            console.log(form.action)
            let formdict = {};
            let form_para= []
            for (var j = 0; j < form.length; j++) {
            let formItem = {};
            input = form[j];
            formItem["nodename"] = input.nodeName;
            formItem["placeholder"] = input.getAttribute("placeholder");
            formItem["type"] = input.type;
            formItem["name"] = input.name;
            formItem["value"] = input.value;
            console.log(formItem);
            form_para.push(formItem);
            } 
            formdict[form.action] = form_para
            console.log("33",formdict)
            formItem_list.push(formdict)
        }
        formdicts["data"] = formItem_list
        return JSON.stringify(formdicts)
                        }
                    ''')
        # #print("575", form_data, type(form_data))
        form_json = json.loads(form_data)

        inputs = self.page.query_selector_all("input")
        textareas = self.page.query_selector_all("textarea")
        if len(form_json["data"]) > 0:
            for form in form_json["data"]:
                # #print("573", form)
                if self.marktag(form, "form"):
                    form_tag = form.values()
                    for tags in form_tag:
                        # #print("577", tags)
                        # tags
                        # [{'nodename': 'INPUT', 'placeholder': None, 'type': 'hidden', 'name': 'name', 'value': 'anonymous user'},
                        # {'nodename': 'TEXTAREA', 'placeholder': None,'type': 'textarea', 'name': 'text', 'value': ''},
                        # {'nodename': 'INPUT', 'placeholder': None, 'type': 'submit', 'name': 'submit', 'value': 'add message'}]
                        for tag in tags:
                            input_name = tag["name"]
                            input_type = tag["type"]
                            input_placeholder = tag["placeholder"]
                            if tag["nodename"] == "INPUT":
                                #print(input_type)
                                input_node_i = self.input_node(
                                    inputs, input_type, input_name, input_placeholder)
                                if input_type == "text":
                                    input_node_i.click()
                                    input_node_i.fill("test")
                                elif input_type == "hidden":
                                    input_node_i.evaluate(
                                        "node => node.value='test'")
                                elif input_type == "submit":
                                    input_node_i.click()
                                elif input_type == "button":
                                    input_node_i.click()
                            elif tag["nodename"] == "TEXTAREA":
                                textarea_node_i = self.textarea_node(
                                    textareas, input_name)
                                if input_type == "textarea":
                                    textarea_node_i.click()
                                    textarea_node_i.fill("test")

    def input_node(self, inputs, n_type, n_name, n_placeholder):
        for i in inputs:
            i_type = i.get_attribute("type")
            i_name = i.get_attribute("name")
            i_placeholder = i.get_attribute("placeholder")

            #print(n_type, n_name, n_placeholder, i_placeholder)
            if i_type == n_type and i_name == n_name:
                return i
            elif i_placeholder:
                if i_type == n_type and i_placeholder == n_placeholder:
                    return i

    def textarea_node(self, textareas, n_name):
        for i in textareas:
            i_name = i.get_attribute("name")
            if i_name == n_name:
                return i

    def find_span(self):
        #print("开启探测span....")
        # 获取span标签
        spans = self.page.query_selector_all("span")
        for i in spans:
            try:
                i_text = i.inner_text()
                # i.get_attribute("class")
                print(i)
                print("span的文本:\t",i_text)
                # self.page.click('span:has-text(\"{}\")'.format(i_text))
                try:
                    i.click()
                except:
                    pass
                # 监听dom变化
                #print("开始监听dom变化....")
                xy_list = self.listening_dom()
                # playwright事件：click\dblclick\down\move\up
                # 页面的事件：click\dblclick\mousedown\mouseout\mouseup
                num = 0
                #print("572。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。")
                #print("循环点击变化的dom....", xy_list)
                if xy_list:
                    for i in xy_list:
                        #print("583", i)
                        num = num+1
                        # #print(num,"获取坐标及动作：",i)
                        self.page.mouse.move(i["x"], i["y"])
                        if i["event"] == "click":
                            self.page.mouse.click(i["x"], i["y"])
                        if i["event"] == "dblclick":
                            self.page.mouse.dblclick(i["x"], i["y"])
                        if i["event"] == "mousedown":
                            self.page.mouse.down()
                        if i["event"] == "mouseup":
                            self.page.mouse.up()
                            # r.sadd("target_url", link)
                        # 获取input的标签 （6.py）
                    # 获取ul
                    listItems = self.page.locator.locator('ul > li')
                    #print(listItems)
                    for i in len(listItems):
                        listItems.nth(i).click()

                    # 获取select的标签
                    selects = self.page.query_selector_all("select")
                    # 获取option内容
                    options = self.page.query_selector_all("option")
                    for select in selects:
                        name = select.get_attribute("name")
                        # #print(name)
                    # 获取单选
                        for option in options:
                            value = option.get_attribute("value")
                            self.page.select_option("#"+name, value, timeout=0)
                    self.input_list()
            except Exception as e:
                traceback.print_exc()
                #print("报错了:", e)

    def close_dialog(self):
        #print("开启探测弹窗....")
        self.page.evaluate('''() => {
   function focusInput() {
    //console.log("注入了button js脚本")
    var elements = document.getElementsByTagName("button");
    //console.log(elements);
    for (var i=0; i < elements.length; i++) {
        //console.log(elements[i].outerHTML);
        if (elements[i].outerHTML.indexOf("dialog") != -1) {
            //console.log(elements[i]);
            elements[i].click();
        }
      }
    }
  setInterval(function() {
    focusInput()
}, 100);
    }''')

    def test_script(self):
        #print("开启注入js脚本....")
        crawlTar.test_css(self)
        self.page.evaluate('''() => {
    console.log("注入了tagFocus js脚本")
    var elements = document.querySelectorAll("input,span,a,link,select,textarea");
    //var elements = document.getElementsByTagName("input");
    //console.log(elements);
    for (var i=0; i < elements.length; i++) {
        elements[i].setAttribute('tabindex',"1")
        //console.log( elements[i])
        //console.log(elements[i],elements[i].onfocus)
        elements[i].onfocus = function() { this.className = 'focusClass'; };
        //elements[i].onfocus = function() { alert("ttttt") };
        //elements[i].onfocus = function() { console.log("bbbbbbbbbbbbb"); };
        //console.log(elements[i],elements[i].onfocus)
        elements[i].onblur = function() { this.className = ''; };
    }
  }''')

    def marktag(self, js_content, source):
        js_dict = {}
        js_dict["js_content"] = js_content
        js_dict["source"] = source
        if js_dict in self.js_content_list:
            return False
        else:
            self.js_content_list.append(js_dict)
            return True

    def parse_link_static(self, link):
        if link.startswith('http'):
            parsedLink = parse.urlparse(link)
            hostname = parsedLink.netloc  # 主机名不带端口号
            path = parsedLink.path
            link = path.split('/')[-1].split('.')[-1]
            if link == '':
                return False
            else:
                blacklists = ['css',  'svg', "png", "gif", "jpg", "mp4", "mp3", "mng", "pct", "bmp", "jpeg", "pst", "psp", "ttf",
                              "tif", "tiff", "ai", "drw", "wma", "ogg", "wav", "ra", "aac", "mid", "au", "aiff",
                              "dxf", "eps", "ps", "svg", "3gp", "asf", "asx", "avi", "mov", "mpg", "qt", "rm",
                              "wmv", "m4a", "bin", "xls", "xlsx", "ppt", "pptx", "doc", "docx", "odt", "ods", "odg",
                              "odp", "exe", "zip", "rar", "tar", "gz", "iso", "rss", "pdf", "txt", "dll", "ico",
                              "gz2", "apk", "crt", "woff", "map", "woff2", "webp", "less", "dmg", "bz2", "otf", "swf",
                              "flv", "mpeg", "dat", "xsl", "csv", "cab", "exif", "wps", "m4v", "rmvb"]
                result = any(link in black for black in blacklists)
                if result == True:
                    return True
                else:
                    return False
        else:
            return True

    def goto(self, target):
        self.page.goto(target, wait_until="networkidle", timeout=600000)
        # 每次打开个新网页，就注入一次js,主要是高亮标签
        # self.page.pause()
        # self.test_script()
        try:
            # self.page.expose_function("test_script", self.test_script)
            # 注册新的函数，以采集请求
            self.page.expose_function("getlink", self.getlink)
            self.page.expose_function("find_a", self.find_a)
        except:
            pass
        # 监听dom变化
        self.listening_dom()
        # 监听事件变化
        self.listening_event()
        # 寻找A标签
        self.find_a()
        # 寻找input标签
        self.input_list()
        # 寻找form表单
        self.get_form_script()
        # 寻找span标签
        # self.find_span()
        # 判断是否有弹窗干扰，关掉
        self.close_dialog()
        # 点击所有包含javascript的标签
        self.all_a_click()

    def run(self, cc):
        self.goto(self.target)
        while self.q.empty() == False:
            q_url = self.q.get()
            # print("[+]"*10+"\t取走数据\t"+q_url)
            self.goto(q_url)
        n = 0
        print("一共爬取了\t{}\t条请求".format(len(self.req_list)))
        for i in self.req_list:
            n = n + 1
            self.sheet.write(n, 0, i["url"])
            self.sheet.write(n, 1, i["method"])
            self.sheet.write(n, 2, json.dumps(i["headers"]))
            self.sheet.write(n, 3, json.dumps(i["body_data"]))
        if file_name:
            self.wbk.save(file_name)
        if args.trace:
            cc.tracing.stop(path=args.trace)
        closeBrowser(browser)

    def login(self,login_script):
        # login_script = login_script.strip('.py')
        # import loginttt
        # loginttt.login_test(self.page)
        first = False
        end = False
        first_line = ""
        end_line = ""
        login_name = ""
        f2_name = "./tmp/"+login_script.split(".")[0]+"_login_test.py"
        with open(login_script,"r") as f, open(f2_name,"w") as f2:
            lines = f.readlines()
            n = 0
            for i in lines:
                n = n + 1
                if first == False:
                    if i.strip().startswith("page.goto"):
                        print(n)
                        first_line = n
                        first = True
                if end == False:
                    if i.strip().startswith("page.close"):
                        print(n)
                        end_line = n
                        end = True
            new_line = lines[first_line:int(end_line)-2]
            new_line_start = '''def login_test(page):
            '''
            f2.write(new_line_start)
            f2.writelines(new_line)
            path,filename = os.path.split(f2_name)
            print(filename)
            login_name = filename.split(".")[0]
        login_name_module = importlib.import_module('tmp.{}'.format(login_name))
        login_name_module.login_test(self.page)
        os.remove(f2_name)

def get_chrome(path):
    if path:
        return path
    else:
        sysstr = platform.system()
        if(sysstr =="Windows"):
            logger.info("The operating system is: Windows")
            executable_path = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            if os.path.exists(executable_path):
                return executable_path
            else:
                #print("Please manually configure the chrome path,E.g --chrome_path")
                sys.exit(1)
        elif(sysstr == "Linux"):
            logger.info("The operating system is: Linux")
        elif(sysstr == "Darwin"):
            logger.info("The operating system is: MacOS")
            executable_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if os.path.exists(executable_path):
                return executable_path
            else:
                #print("Please manually configure the chrome path,E.g --chrome_path")
                sys.exit(1)
        else:
            print ("Other System tasks")
def str_bool(str):
    if str.lower() == "true":
        return True
    elif str.lower() == "false":
        return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='biu~biu~biu~')
    parser.add_argument('--target', default='',help='crawler target site')
    parser.add_argument('--slow_mo', default=100,help='Crawl speed,The unit is milliseconds')
    parser.add_argument('--headless', default="True",help='Whether to display the browser interface')
    parser.add_argument('--devtools', default="False",help='Whether to enable development and debugging')
    parser.add_argument('--login', default=False,help='import login script path,E.g --login oa_login.py')
    parser.add_argument('--chrome_path',help='configure the chrome path')
    parser.add_argument('--proxy', default="",help='Network proxy mode,E.g http://127.0.0.1:8089 or socks5://127.0.0.1:10808')
    parser.add_argument('--trace',help='Track the crawling process for replay,E.g trace_test.zip')
    parser.add_argument('--out_xls',help='result to output .xls')
    args = parser.parse_args()
    if len(sys.argv)==1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    file_name = args.out_xls
    # tarurl = "https://element.eleme.cn/#/zh-CN/component/select"
    # tarurl = "https://bsec.flashexpress.pub/#/distance/distance_tag"
    tarurl = args.target
    # tarurl = "http://testphp.vulnweb.com"
    # PROXY_HTTP = "http://127.0.0.1:8089"
    q = Queue(maxsize=0)
    browserConfig = {"slow_mo": int(args.slow_mo),
                     "headless": str_bool(args.headless),
                     "devtools": str_bool(args.devtools),
                     #  "executable_path":"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    #   "executable_path":"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      "executable_path":get_chrome(args.chrome_path),
                     #    "proxy": {"server": "http://127.0.0.1:8089"},
                        # "proxy": {"server": ""},
                     #  "proxy": {"server": "socks5://127.0.0.1:10808"},
                     "args": [
                         "--disable-gpu",
                         "--disable-web-security",
                         "--disable-xss-auditor",  # 关闭 XSS Auditor
                         "--no-sandbox",
                         "--disable-setuid-sandbox",
                         "--allow-running-insecure-content",  # 允许不安全内容
                         "--disable-webgl",
                         "--disable-popup-blocking"
                     ]
                     }
    if args.proxy:
        proxy = {"server": args.proxy}
        browserConfig.update(proxy)
    # 初始化浏览器
    #print(browserConfig)
    browser = initBrowser(browserConfig=browserConfig)
    # 第一次打开目标
    # firstOpen(tarurl)
    # 初始化page
    page2222, cc = initPage(browser=browser)
    ss = crawlTar(page2222, tarurl)
    if args.login:
        ss.login(args.login)
    ss.run(cc)
