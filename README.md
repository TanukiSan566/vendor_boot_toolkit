# vendor_boot 解包/打包工具（GitHub Actions 版）

给 Windows 用户用的 vendor_boot.img（header v4，多 ramdisk 分段那种）解包/编辑/
重新打包工具。不用装 Linux、不用装 WSL，全程靠 GitHub 网页操作 + Actions 云端
跑脚本。

## 怎么用

### 第一步：建一个仓库，把这些文件传上去

新建一个 GitHub 仓库（私有的也行），把这个压缩包解压后的所有内容
（`scripts/`、`.github/`、这个 README）都传上去，保持目录结构不变。

### 第二步：解包

1. 在仓库根目录建一个 `input` 文件夹，把你的 `vendor_boot.img` 放进去，
   改名叫 `input/vendor_boot.img`
2. 网页上 commit / push 这个改动（或者用"Add file → Upload files"直接传）
3. 去仓库的 **Actions** 标签页，等 "Unpack vendor_boot" 这个流程跑完（一般
   一两分钟），点进这次运行，页面最下面 **Artifacts** 里下载 `unpacked` 这个
   zip
4. 解压下载下来的 zip，就能看到：
   ```
   metadata.json              <- 记录了所有打包需要的参数，不要手动改
   dtb.bin
   bootconfig.bin
   fragments/
     platform/                <- 正常开机会用到的部分
       init.rc
       system/etc/recovery.fstab
       ...
     recovery/                <- 进TWRP才会额外加进来的部分（TWRP本体）
       init.recovery.usb.rc
       twres/ui.xml
       ...
   ```
   这时候 `fragments/` 下面就是普通的文件夹和文本文件了，随便用记事本/
   VSCode/Notepad++改，改完保存就行。

### 第三步：改完之后重新打包

1. 把整个改完的文件夹（包括 `metadata.json`），原样放进仓库根目录下的
   `edited` 文件夹（也就是 `edited/metadata.json`、
   `edited/fragments/platform/...` 这样）
2. push
3. 去 Actions 页面等 "Repack vendor_boot" 跑完，下载 `vendor_boot_repacked`
   这个 artifact，里面的 `vendor_boot_repacked.img` 就是改好的新镜像，
   `fastboot flash vendor_boot_a vendor_boot_repacked.img` 刷进去就行

### 如果某个分段改完变太大，分区装不下

默认每个分段用原来的压缩格式重新压。如果想强制换成压缩率更高的 zstd
（前提是你的设备内核认得 zstd，参考之前跟 Claude 聊过的判断方法——搜
dmesg 里有没有 `kmod_zstd` 在 `Trying to unpack rootfs image as initramfs`
之前初始化），去 Actions 页面手动点 **Run workflow**（不是 push 触发），
在 `codec_overrides` 那一栏填 `platform=zstd,recovery=zstd`（哪个分段就填
哪个，不用全填）。

## 第四步（可选）：修复"能进TWRP但选重启到系统就死循环"

这是 hovatek 这类最小 manifest 在线编译工具的一个通病：编译出来的
vendor_boot 里，PLATFORM 分段（正常开机要用到的那部分）内容经常是残缺的，
因为编译环境本身没有完整的原厂 vendor 源码树可以用来生成它。表现是：能
正常进 TWRP（RECOVERY 分段几乎补全了所有运行环境），但选"重启到系统"就
无限重启回 TWRP，拔电池也没用。

对应 **"Graft PLATFORM fragment (fix bootloop)"** 这个 workflow：

1. 把你手上原厂的 `vendor_boot.img`（没刷过 TWRP 之前，通过官方下载工具/
   分区导出拿到的那份）放进仓库 `input/donor_stock_vendor_boot.img`
2. 把刚编译出来的 `vendor_boot.img` 放进
   `input/fresh_build_vendor_boot.img`
3. push，等 workflow 跑完，下载 `vendor_boot_grafted` 这个 artifact
4. 里面的 `vendor_boot_grafted.img` 就是 PLATFORM 分段换成原厂真实内容、
   RECOVERY 分段保留你刚编译那份 TWRP 的最终镜像，直接
   `fastboot flash vendor_boot_a` 刷进去

这一步全程不解压、不碰任何文件内容，纯粹是在压缩状态下把两个分段的字节
拼到一起，两边各自的压缩格式（不管原来是 lz4 还是 zstd）都原样保留，
风险比手动解包改文件再重新压缩要低得多。

## 目录结构

```
scripts/
  codec.py            自动识别/压缩解压 lz4-legacy 和 zstd 两种格式
  cpio_extract.py      cpio (newc格式) 解包
  cpio_pack.py          cpio (newc格式) 打包
  lz4legacy.py           legacy lz4 解压
  lz4legacy_compress.py  legacy lz4 压缩
  zstd_wrap.py            zstd 压缩/解压
  vboot_unpack.py         主入口：vendor_boot.img -> 文件夹
  vboot_repack.py         主入口：文件夹 -> vendor_boot.img
  vboot_graft_platform.py 主入口：两个vendor_boot.img -> 移植了PLATFORM分段的新镜像
.github/workflows/
  unpack.yml             对应第二步的自动化流程
  repack.yml             对应第三步的自动化流程
  graft-platform.yml      对应第四步的自动化流程（修复死循环）
```

## 限制/注意事项

- 只支持 **header_version 4** 的 vendor_boot（多 ramdisk 分段，Android 12+
  动态分区机型常见的格式）。header v2/v3 或者普通 boot.img 这个工具不认。
- GitHub 单个文件超过 100MB 直接 push 会被拒绝，如果你的 vendor_boot.img
  本身超过 100MB，需要额外配置 Git LFS（这个工具本身没做，需要自己在仓库
  设置里开）。
- 每次 unpack/repack 都是全新的云端环境，不会保留上一次的中间文件，改动
  完全靠你自己在 `edited/` 里维护。
