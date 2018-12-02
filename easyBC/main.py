﻿from easyBC import orders
from easyBC import Portfolio as pf
from pylab import *
import tushare as ts
from easyBC import statistics
from tools.to_mysql import ToMysql
from easyBC import Deal


class main(object):
    def __init__(self):
        self.securities = ['603912.SH', '300666.SZ', '300618.SZ', '002049.SZ', '300672.SZ']     # 回测标的
        self.capital = 100000000    # 初始本金
        self.start_date = '2018-03-01'  # 回测开始时间
        self.end_date = '2018-04-01'  # 回测结束时间
        self.period = 'd'   # 策略运行周期, 'd' 代表日, 'm'代表分钟  现在还没有m
        # 建回测时间序列
        ts.set_token('502bcbdbac29edf1c42ed84d5f9bd24d63af6631919820366f53e5d4')
        pro = ts.pro_api()
        back_test_date_start = (datetime.datetime.strptime(self.start_date, '%Y-%m-%d')).strftime('%Y%m%d')
        back_test_date_end = (datetime.datetime.strptime(self.end_date, "%Y-%m-%d")).strftime('%Y%m%d')
        df = pro.trade_cal(exchange_id='', is_open=1, start_date=back_test_date_start, end_date=back_test_date_end)
        self.date_temp = list(df.iloc[:, 1])
        self.date_seq = [(datetime.datetime.strptime(x, "%Y%m%d")).strftime('%Y-%m-%d') for x in self.date_temp]

    # 准备工作#################################################
    # 建立数据库连接,设置tushare的token,定义一些初始化参数

    def initialize(self):
        db = ToMysql()
        # 先清空之前的测试记录,并创建中间表
        sql_wash1 = 'delete from my_capital'
        db.execute(sql_wash1)
        sql_wash2 = 'delete from my_position'
        db.execute(sql_wash2)
        sql_wash3 = 'truncate table my_stock_pool'
        db.execute(sql_wash3)
        sql_setCash = "INSERT INTO my_capital VALUES (%s, %s, 0, 0, %s)"\
                     % (repr(self.start_date), self.capital, self.capital)
        db.execute(sql_setCash)
        sql_insert = "insert into my_position(trdate,code,cost_price,revenue,volume,amount,margin,side) " \
                     "VALUES ('%s','%s',%.2f,%.2f,%.2f,%.2f,%.2f,'%s')" \
                     % (self.date_seq[0], "cash", 1, 0, self.capital, self.capital, 0,"buy")
        db.execute(sql_insert)
        db.close()

    def get_bars(self, trdate):
        db = ToMysql()
        # 清空行情源表，并插入新的相关股票的行情数据。该操作是为了提高回测计算速度而剔除行情表(stock_all)中的冗余数据。
        sql_wash4 = 'truncate table stock_info'
        db.execute(sql_wash4)
        in_str = '('
        for x in range(len(self.securities)):
            if x != len(self.securities) - 1:
                in_str += str('\'') + str(self.securities[x]) + str('\',')
            else:
                in_str += str('\'') + str(self.securities[x]) + str('\')')

        sql_insert = "insert into stock_info(select * from stock_all a where a.stock_code in %s and a.state_dt = '%s')" \
                     % (in_str,trdate)
        db.execute(sql_insert)
        db.close()

    def go(self):
        # 开始模拟交易
        day_index = 0
        for i in range(0, len(self.date_seq)):

            day_index += 1
            if i ==0:
                self.initialize()
            else:
                self.get_bars(self.date_seq[i-1])
                self.update_daily(self.date_seq[i-1], self.date_seq[i])  # 更新估值表

            self.handle_data(self.date_seq[i], self.securities)

            ###### 每5个交易日运行一次自定义交易函数，这里是更新一次配仓比例 ()
            if divmod(day_index + 5, 5)[1] == 0:
                self.schedule(self.date_seq[i], self.securities)
            print('Runnig to Date :  ' + str(self.date_seq[i]))
        print('ALL FINISHED!!')


    def handle_data(self,trdate, context):
        for stock in self.securities:
            try:
                ##ans2 = ev.model_eva(stock, trdate, 90, 365)
                ##这里其实没啥用，懒得写了，仅仅用作示例，后续换成其他的就好了
                # print('Date : ' + str(date_seq[i]) + ' Update : ' + str(stock))
                pass
            except Exception as ex:
                print(ex)

    def schedule(self,trdate, context):
        # 定期运行函数####
        portfolio_pool = context
        pf_src = pf.get_portfolio(portfolio_pool, trdate, 250)
        # 取最佳收益方向的资产组合
        risk = pf_src[1][0]
        weight = pf_src[1][1]
        orders.change_to(portfolio_pool, trdate, weight)

    def change_securities(self,code_list):
        self.securities = code_list

    def update_daily(self,state_dt_1, state_dt):
        db = ToMysql()
        deal_daily = Deal.Deal(state_dt_1)
        new_holding_value =0
        # 更新position表
        for i in deal_daily.stock_pool:
            if i == "cash":
                new_trdate = state_dt
                new_amount = deal_daily.stock_amount["cash"]
                new_cost_price = 1
                new_revenue = 0
                new_margin = 0
                new_side = "buy"
                new_volume = deal_daily.stock_volume["cash"]
                sql_insert = "insert into my_position(trdate,code,cost_price,revenue,volume,amount,margin,side) " \
                             "VALUES ('%s','%s',%.2f,%.2f,%.2f,%.2f,%.2f,'%s')" \
                             % (new_trdate, "cash", new_cost_price, new_revenue, new_volume, new_amount, new_margin, new_side)
                db.execute(sql_insert)

            else:
                sql_bars = "select * from stock_info a where a.state_dt = '%s' and a.stock_code = '%s'" % (
                    state_dt_1, i)
                done_set_buy = db.select(sql_bars)
                pct_change = done_set_buy[0][10]/100+1
                new_price = done_set_buy[0][3]
                new_trdate = state_dt
                new_amount = pct_change*deal_daily.stock_amount[i]
                new_cost_price = deal_daily.stock_cost_price[i]
                new_revenue = (pct_change-1)*deal_daily.stock_amount[i] + deal_daily.stock_revenue[i]
                new_margin = deal_daily.stock_margin[i]
                new_side = deal_daily.stock_side[i]
                new_volume = new_amount/new_price
                new_holding_value = new_holding_value + new_amount
                sql_insert = "insert into position(trdate,code,cost_price,revenue,volume,amount,margin,side) " \
                             "VALUES ('%s','%s',%.2f,%.2f,%.2f,%.2f,%.2f,'%s')" \
                             % (new_trdate, i, new_cost_price, new_revenue,new_volume, new_amount, new_margin, new_side)
                db.execute(sql_insert)

        # 更新账户表my_capital
        new_available_fund = deal_daily.cur_available_fund  # 现金不变。
        new_capital = new_available_fund + new_holding_value
        new_margin = 0  # 先不填这个坑
        sql_insert = "insert into my_capital(date,available_fund,holding_value,margin,total_asset) " \
                     "VALUES ('%s',%.2f,%.2f,%.2f,%.2f)" \
                     % (state_dt, new_available_fund, new_holding_value, new_margin, new_capital)
        db.execute(sql_insert)
        return 1

    def afterbc(self):
        db = ToMysql()
        sharp, c_std = statistics.get_sharp_rate()
        print('Sharp Rate : ' + str(sharp))
        print('Risk Factor : ' + str(c_std))

        sql_show_btc = "select * from stock_index a where a.stock_code = '000001.SH' and a.state_dt >= '%s' and a.state_dt <= '%s' order by state_dt asc" % (
        self.start_date, self.end_date)
        done_set_show_btc = db.select(sql_show_btc)
        # btc_x = [x[0] for x in done_set_show_btc]
        btc_x = list(range(len(done_set_show_btc)))
        btc_y = [x[3] / done_set_show_btc[0][3] for x in done_set_show_btc]
        dict_anti_x = {}
        dict_x = {}
        for a in range(len(btc_x)):
            dict_anti_x[btc_x[a]] = done_set_show_btc[a][0]
            dict_x[done_set_show_btc[a][0]] = btc_x[a]

        # sql_show_profit = "select * from my_capital order by state_dt asc"
        sql_show_profit = "select max(a.capital),a.state_dt from my_capital a where a.state_dt is not null group by a.state_dt order by a.state_dt asc"
        done_set_show_profit = db.select(sql_show_profit)
        profit_x = [dict_x[x[1]] for x in done_set_show_profit]
        profit_y = [x[0] / done_set_show_profit[0][0] for x in done_set_show_profit]

        # 绘制收益率曲线（含大盘基准收益曲线）
        def c_fnx(val, poz):
            if val in dict_anti_x.keys():
                return dict_anti_x[val]
            else:
                return ''

        fig = plt.figure(figsize=(20, 12))
        ax = fig.add_subplot(111)
        ax.xaxis.set_major_formatter(FuncFormatter(c_fnx))

        plt.plot(btc_x, btc_y, color='blue')
        plt.plot(profit_x, profit_y, color='red')
        plt.show()
        db.close()

if __name__ == '__main__':
    a=main()
    a.go()






