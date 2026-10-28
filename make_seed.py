"""Build the optional import file from the company research already reviewed in this chat."""
import csv
from pathlib import Path
rows=[
('REECONS Engineering','nguyentuan@reecons.vn','+84 28 3620 3625','https://reecons.vn/contact/','central Chiller systems, process cooling water and MEP maintenance','中央Chiller、工艺冷却水及机电维护','官网产品推荐／招标采购邮箱。其他：info@reecons.vn；yoanguyon@reecons.vn'),
('Đoàn Nhất M&E','info@doannhat.com','+84 28 3842 3271','https://www.doannhat.com/vi/lien-he.html','Chiller and mechanical installation services','Chiller及机电安装','另一电话：+84 28 3842 3272'),
('R.E.E M&E','ree@reeme.com.vn','+84 28 3810 0068','https://www.reeme.com.vn/contact','commercial and industrial M&E design and installation','商业及工业机电设计安装','大型项目需确认品牌准入。'),
('WASOL','info@wasol-vn.com','+84 906 688 934','https://wasol-vn.com/contact/','Chiller, cooling and heat-exchange design-and-build services','Chiller、冷却及换热系统设计施工','固定电话：+84 28 3961 0884'),
('LQC M&E','vkngan.lqc@gmail.com','+84 369 830 596','https://lqcvn.vn/','HVAC installation and maintenance covering Chiller, AHU and FCU systems','Chiller、AHU和FCU相关HVAC安装及维护','Zalo：https://zalo.me/0369830596'),
('Hoàng Nguyên Anh','xuangiap@hoangnguyenanh.com','+84 982 923 986','https://hoangnguyenanh.com/','industrial and chilled-water piping installation services','工业及冷冻水管道安装','先确认阀门由自身、总包还是业主采购。'),
('Nam Thịnh MER','contact@namthinh.com.vn','+84 28 3883 2999','https://www.namthinh.com.vn/','mechanical, electrical and refrigeration contracting services','机电及冷冻工程承包','另一电话：+84 28 3883 2989'),
('Ricons','contact@ricons.vn','+84 28 3514 0349','https://www.ricons.vn/','M&E services for commercial buildings and industrial facilities','商业建筑和工业设施机电服务','请总邮箱转接机械材料或采购团队。'),
('Searefico','info@searefico.com','+84 28 3822 7260','https://searefico.com/','mechanical engineering and industrial refrigeration activities','机电工程及工业制冷业务','集团入口，需要转接Searefico E&C工程或采购部门。'),
('Hawee M&E','hawee-me@hawee.com.vn','+84 28 2215 1117','https://hawee.com.vn/lien-he','M&E construction and maintenance activities in southern Vietnam','越南南部机电施工及维护','本地电话；集团总部：+84 24 3311 7744'),
('Takasago Vietnam','hcm@tte-net.com','+84 28 6281 4475','https://takasago.vn/en/contact-us.html','air-conditioning, ventilation and plumbing design-and-construction services','空调、通风及给排水设计施工','胡志明市办公室邮箱。'),
('Taikisha Vietnam','tvemktg@taikisha-vn.com','+84 28 3899 4703','https://www.taikishavietnam.com.vn/en/contact','HVAC and process utility services, including cooling-water systems','HVAC及工艺冷却水公用系统服务','胡志明市办公室，商务邮箱。'),
('Kinden Vietnam','','+84 28 3933 0121','https://www.kinden.com.vn/','air-conditioning and industrial cooling-water services','空调及工业冷却水工程','业务邮箱未核实。请先电话索取；勿使用招聘邮箱。'),
('SAREE','saree@vnn.vn','+84 909 026 262','https://sareeref.vn/en/','industrial refrigeration installation and water-cooling services','工业制冷安装及水冷系统服务','仅推荐水侧应用。固定电话：+84 28 3754 7607／7608'),
('Hợp Nhất M&E','hopnhat@hopnhatme.com','+84 908 407 631','https://hopnhatme.com/contact-us/','Chiller and central air-conditioning solutions','Chiller及中央空调解决方案','固定电话：+84 28 3811 8653／8656／8683'),
('Shinryo Vietnam','shinryovietnam@shinryovn.com','+84 28 3930 0847','https://www.shinryovietnam.com/contact-us/','Chiller plant, hot-water supply and process cooling-water services','Chiller机房、热水供应及工艺冷却水服务','商务邮箱；svn@shinryovn.com为招聘邮箱。另一电话：+84 28 3930 0848'),
('Kurihara Vietnam','hcm@kurihara.vn','+84 28 3999 0841','https://kurihara.vn/contact-me-contractor-kurihara-vietnam/','mechanical engineering, installation and maintenance services','机械工程、安装及维护服务','本地电话末尾另有0842／0843／0844；总部hn@kurihara.vn。'),
('YOCO M&E','info@yoco.vn','+84 967 927 927','https://codienlanh.com/lien-he/','central air-conditioning and Chiller installation services','中央空调及Chiller安装服务','官网另列info@codienlanh.com；固话仍为旧格式08 6295 8806。'),
('GLT / Toàn Cầu','info@toancau.vn','+84 28 3770 1055','https://toancau.vn/','data centre infrastructure and cooling-system services','数据中心基础设施及冷却系统服务','工程公司GLT，与Toàn Cầu Pumps不同。'),
('TECHGEL','info@techgel.com','+84 28 3510 7030','https://www.techgel.com/vi/contact-us','HVAC, plumbing and industrial engineering services','HVAC、给排水及工业工程服务','2025公司资料另列techgel@techgel.com。'),
('NSN Construction & Engineering','contact@nsn.com.vn','+84 28 2200 2809','https://nsn.vn/en/','HVAC construction, including Chiller systems for data centres','包括数据中心Chiller系统的HVAC施工','胡志明市代表处。'),
('Sanyo Vietnam','info@secvn.com','+84 28 6291 5386','https://www.secvn.com/nha-may-san-xuat','industrial installation project work in Vietnam','越南工业安装工程','先确认水系统采购范围。旧备用邮箱sechcm@secvn.com需复核。'),
('Gia Nguyễn HVAC','info@gnair.vn','+84 979 007 003','https://gnair.vn/lien-he','HVAC installation and maintenance project work','HVAC安装及维护项目','Phước Thắng，原头顿区域。项目thanh.nguyen@gnair.vn；批发nga.nguyen@gnair.vn / +84 906 008 818。'),
('Nam Xuân Phong','springaireng@gmail.com','+84 943 999 006','https://www.yellowpages.vn/lgs/710052/co-dien-lanh-nam-xuan-phong---cong-ty-tnhh-co-dien-lanh-nam-xuan-phong.html','listed chilled-water piping and pump installation services','目录中列出的冷冻水管道及泵系统安装','目录资料较旧、号码需复核；未核实独立官网。'),
('An Nhiên HVAC','','+84 938 347 322','https://dauthau.asia/businesslistings/detail/CONG-TY-TNHH-AN-NHIEN-HVAC-125950/','published Chiller maintenance project experience','公开的Chiller维护项目经验','登记电话需复核，未取得业务邮箱。税号0314386675。'),
('Minh Dũng / White Cool','tranminhchiller@gmail.com','+84 981 686 939','https://whitecool.vn/','White Cool Chiller manufacturing, installation and maintenance services','White Cool的Chiller制造、安装及维护服务','周边客户：81D, Ấp 1, Lương Hòa, Tây Ninh。业务+84 989 228 227／+84 919 597 425。')]
root=Path(__file__).resolve().parent/'assets';root.mkdir(exist_ok=True)
with (root/'胡志明市工程客户.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['客户编号','公司名称','国家／地区','邮箱','电话','官网','备注','主题','英文正文','中文翻译'])
 for i,(name,email,phone,website,en,cn,note) in enumerate(rows,1):
  subject=f'Water-System Balancing Valves for {name}'
  body=f'Dear {name} Team,\n\nI’m BaiJiang Lin from FriesGo Global. I noticed your {en}.\n\nWe supply lockable manual balancing valves, self-operated differential pressure control valves, and self-operated flow control valves for suitable water circuits.\n\nWhere your projects include chilled-water or hot-water circulation, we would like to discuss valve supply for branch balancing, installation, and maintenance replacement.\n\nCould you introduce us to the responsible engineering or purchasing team? I can provide our catalogue and inspection reports for review.\n\nBest regards,\nBaiJiang Lin | FriesGo Global\nfriesgoglobal@gmail.com'
  translation=f'{name}团队，您好：\n\n我是FriesGo Global的BaiJiang Lin。了解到贵公司的{cn}。\n\n我们供应数字锁定平衡阀、自力式压差控制阀和自力式流量控制阀，供符合产品工况要求的水回路使用。\n\n如果贵公司的项目包含冷冻水或热水循环，希望探讨支路平衡、安装及维护更换所需阀门的供应合作。\n\n能否介绍负责的工程或采购团队？我们可以提供目录及检验报告供审核。'
  w.writerow([f'FGVN{i:04d}',name,'越南',email,phone,website,'资料核查日期：2026-10-24；未实拨／未测试投递。'+note,subject,body,translation])
