## python 实现的简单反代

### 使用

#### 修改`SERVER_ADDR = ('', 9876)`

server.py 中写 '0.0.0.0'

client.py 中写服务器的外网地址就好。

windows填的ip不要填空，比如`('', 12345)`，会出问题。

#### 修改 client 文件 run 函数

`messages` 列表里面是需要被代理的端口信息。
每个dict代表一个端口信息。
```python
{
    'type': "CONNECTOR", # 表示一个通道，这个不变
    'local_addr':'splay.luobotou.org', # 本地服务的地址
    'local_port':'5000', # 本地服务的端口
    'remote_addr':'0.0.0.0', # 服务器监听的地址
    'remote_port':'21354' # 服务器监听的端口
},
```
端口代理成功后，通过`xx.xx.xx.xx:21355`可以利用client访问到内网服务。

