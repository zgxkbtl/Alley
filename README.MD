## python 实现的简单反代

### 使用

#### 修改`SERVER_ADDR = ('192.168.3.47', 9876)`

改为服务器的地址，client和server都要改。
windows不要填的ip不要填空，比如`('', 12345)`，会出问题。
最好也不要填本地回环。

#### 修改 client 文件 run 函数

`messages` 列表里面是需要被代理的端口信息。
每个dict代表一个端口信息。
```python
{
    'local_addr':'www.baidu.com', # 内网服务地址
    'local_port':'80', # 内网服务端口
    'remote_addr':'192.168.3.47', # server暴露地址
    'remote_port':'21355' # server暴露端口
}
```
端口代理成功后，通过`192.168.3.47:21355`可以利用client访问到内网服务。

#### client不能访问对应server的暴露ip

由于ip用来区分client了，所以不支持client再访问代理的端口。（本来就是脱裤子放屁

