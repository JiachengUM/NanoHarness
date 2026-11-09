# hwhms项目说明

## 模块简要说明

- api.py: 对外的api，是调用的入口
- car_a: 车厂a的算法代码
  - [core.py](./car_a/core.py): 最终发版的算法，需要充分测试和小心。
    owner: Yichen Wei。
  - [run_test.py](./car_a/run_test.py): 用于最终发版的完整测试。需要很高质量。
    零零碎碎的小实验的测试可以引用或者copy这里的代码，但不要混淆进来。
    owner: Yichen Wei -> ???
- common: 通用的内容，跟车厂无关
- tests: code example and functional test, 不做真正有意义的事情。
- datasets: 存放所有的重要测试数据以及生成数据的过程（代码）。注意，数据不可以提交进入git。所有开发者手动维护其下的数据，大家保持一致。
  - [process.py](./datasets/process.py): 数据处理的通用代码。有一定通用性，不太重要，随写随用。
- exps: 所有的实验。每个实验的目标，和函数名字有明确的意义。不同的实验代码隔离开。
     其中的算法代码基于core随便改，但不要大幅度的copy，只修改必要的部分，尽量复用core。举例，core中有car_control_category，可以copy过来随便改，但不能改core。

## 整体思路

类别需要精确定义，在数据生成和分类的过程中尽量统一和复用。

数据生成（线程）：主要由jiacheng和wangdong执行，整体思路和工程质量yichen会整体看，少量参与。

算法实验（线程）：主要由ziyang和yichen执行。

这两个线程高度同步。数据和算法都是动态提升的。


## 开发者注意事项

基础分支统一使用hwhms，main分支是受保护的。

跟main分支的同步由 wei yichen负责。

各自开发时，必须建立新分支。经过weiyichen review后再merge回到hwhms分支。

分支的名字为hwhms_name。name必须有意义，不能是类似于09.28。

comiit message也必须有意义。能读懂的，不需要读代码也大概知道这个commit干了什么。

算法实验的一些原则:

- 一点点扩充：逻辑(if-else)、提示词（类别说明，examples, 各种例外情况的说明），逐步测试验证其作用，得有客观的，量化的证据说明，这些证据需要远远详细过某几个指标。单纯的指标不能作为证据。
- 所有的实验都需要可以复现，那怕失败的。
