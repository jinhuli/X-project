﻿# encoding: UTF-8
from easyBC import orders
from easyBC import Portfolio as pf
from pylab import *
import tushare as ts
from easyBC import statistics
from tools.to_mysql import ToMysql
from easyBC import Deal
from datetime import datetime
from easyBC import statistics
import pandas as pd
import matplotlib.pyplot as plt
from WindPy import *
w.start()

def getBuylist(code_list,datee):
    data = w.wss(code_list, "pe_ttm,risk_lossvariance120,fa_roicebit_ttm,fa_orgr_ttm,fa_cfogr_ttm","tradeDate=" +datee)
    dataRank=data.rank()
    dataRank["RISK_VARIANCE120_1"]=dataRank.apply(lambda x: (len(dataRank)-x["RISK_VARIANCE120"]+1),axis=1)
    dataRank['Row_sum'] = dataRank.apply(lambda x: (x["FA_ROICEBIT_TTM"]+x["FA_ORGR_TTM"]+x["FA_TATURN_TTM"]+x["FA_NETPROFITMARGIN_TTM"]+x["FA_FCFFPS"]+x["RISK_VARIANCE120_1"])/6,axis=1)
    dataRank = dataRank.sort_values(by='Row_sum')
    buyList = dataRank.iloc[-30:-1,].index.tolist()
    return buyList

class main(object):
    def __init__(self):
        self.securities = ["600016.SH","600020.SH","600015.SH","600021.SH","600017.SH","600022.SH","600012.SH"]     # 回测标的
        self.capital = 100000000    # 初始本金
        self.start_date = '2018-01-01'  # 回测开始时间
        self.end_date = '2018-12-01'  # 回测结束时间
        self.period = 'd'   # 策略运行周期, 'd' 代表日, 'm'代表分钟  现在还没有m
        # 建回测时间序列
        ts.set_token('502bcbdbac29edf1c42ed84d5f9bd24d63af6631919820366f53e5d4')
        self.pro = ts.pro_api()
        back_test_date_start = (datetime.strptime(self.start_date, '%Y-%m-%d')).strftime('%Y%m%d')
        back_test_date_end = (datetime.strptime(self.end_date, "%Y-%m-%d")).strftime('%Y%m%d')
        df = self.pro.trade_cal(exchange_id='', is_open=1, start_date=back_test_date_start, end_date=back_test_date_end)
        self.date_temp = list(df.iloc[:, 1])
        self.date_seq = [(datetime.strptime(x, "%Y%m%d")).strftime('%Y-%m-%d') for x in self.date_temp]

    # 准备工作#################################################
    # 建立数据库连接,设置tushare的token,定义一些初始化参数

    def initialize(self):
        db = ToMysql()
        # 先清空之前的测试记录,并创建中间表
        sql_wash1 = 'delete from my_capital'
        db.execute(sql_wash1)
        sql_wash2 = 'delete from my_position'
        db.execute(sql_wash2)
        sql_wash3 = 'delete from stock_info'
        db.execute(sql_wash3)
        sql_wash4 = 'delete from orders'
        db.execute(sql_wash4)
        sql_setCash = "INSERT INTO my_capital VALUES (%s, %s, 0, 0, %s)"\
                     % (repr(self.date_seq[0]), self.capital, self.capital)
        db.execute(sql_setCash)
        sql_insert = "insert into my_position(trdate,code,cost_price,revenue,volume,amount,margin,side) " \
                     "VALUES ('%s','%s',%.2f,%.2f,%.2f,%.2f,%.2f,'%s')" \
                     % (self.date_seq[0], "cash", 1, 0, self.capital, self.capital, 0,"buy")
        db.execute(sql_insert)
        db.close()
        self.get_bars(self.date_seq[0])

    def get_bars(self, trdate):
        ts.set_token('502bcbdbac29edf1c42ed84d5f9bd24d63af6631919820366f53e5d4')
        pro = ts.pro_api()
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
        # 数据完整性检查
        sql_select = "select * from stock_info"
        bars = db.select(sql_select)
        bar_list =[]
        for i in bars:
            bar_list.append(i[1])

        needupdatelist = list(set(self.securities) - set(bar_list))

        for i in needupdatelist:
            try:
                df = pro.daily(ts_code=i, trade_date=trdate)
                time.sleep(0.3)
                c_len = df.shape[0]
            except Exception as aa:
                print(aa)
                print('No DATA Code: ' + str(i))
                continue
            for j in range(c_len):
                resu0 = list(df.iloc[c_len - 1 - j])
                resu = []
                for k in range(len(resu0)):
                    if str(resu0[k]) == 'nan':
                        resu.append(-1)
                    else:
                        resu.append(resu0[k])
                state_dt = (datetime.datetime.strptime(resu[1], "%Y%m%d")).strftime('%Y-%m-%d')
                try:
                    sql_insert = "INSERT INTO stock_all(state_dt,stock_code,open,close,high,low,vol,amount,pre_close,amt_change,pct_change) VALUES ('%s', '%s', '%.2f', '%.2f','%.2f','%.2f','%i','%.2f','%.2f','%.2f','%.2f')" % (
                        state_dt, str(resu[0]), float(resu[2]), float(resu[5]), float(resu[3]), float(resu[4]),
                        float(resu[9]), float(resu[10]), float(resu[6]), float(resu[7]), float(resu[8]))

                    sql_insert2 = "INSERT INTO stock_info(state_dt,stock_code,open,close,high,low,vol,amount,pre_close,amt_change,pct_change) VALUES ('%s', '%s', '%.2f', '%.2f','%.2f','%.2f','%i','%.2f','%.2f','%.2f','%.2f')" % (
                        state_dt, str(resu[0]), float(resu[2]), float(resu[5]), float(resu[3]), float(resu[4]),
                        float(resu[9]), float(resu[10]), float(resu[6]), float(resu[7]), float(resu[8]))

                    db.execute(sql_insert)

                    db.execute(sql_insert2)
                except Exception as err:
                    continue

        db.close()


    def go(self):
        # 开始模拟交易
        day_index = 0
        for i in range(0, len(self.date_seq)):

            day_index += 1
            if i ==0:
                self.initialize()
            else:

                self.update_daily(self.date_seq[i-1], self.date_seq[i])  # 更新估值表
                self.get_bars(self.date_seq[i])

            self.handle_data(self.date_seq[i], self.securities)

            ###### 每22个交易日运行一次自定义交易函数，这里是更新一次配仓比例 ()
            if divmod(day_index + 4, 22)[1] == 0:
                self.schedule(self.date_seq[i], self.securities)
            print('Runnig to Date :  ' + str(self.date_seq[i]))
        print('ALL FINISHED!!')


    def handle_data(self,trdate, context):
        pass

    def schedule(self,trdate, context):
        # 定期运行函数####
        bar_datetime_str = trdate
        bar_datetime_str1 = w.tdaysoffset(1, bar_datetime_str, "").Data[0][0].strftime('%Y-%m-%d')
        bar_datetime_num = (datetime.strptime(trdate, "%Y-%m-%d")).strftime('%Y%m%d')
        code_list_1 = getBuylist(context,bar_datetime_str)
        self.change_securities(code_list_1)  # 改变证券池
        # 剔除涨停的股票
        bar_data_df = self.get_bars(trdate)
        lt_95_code = bar_data_df[bar_data_df['pctchg'] < 9.5]['code'].tolist()  # 获取行情中涨跌幅小余9.5%的股票
        buy_stock = list(set(lt_95_code) & set(code_list_1))  # 取交集，即要买且涨跌幅小余9.5%的股票
        orders.change_to(buy_stock,trdate)


    def change_securities(self,code_list):
        self.securities = code_list

    def update_daily(self,state_dt_1, state_dt):
        db = ToMysql()


        deal_daily = Deal.Deal(state_dt_1)
        new_holding_value =0
        # 更新position表
        for i in deal_daily.stock_pool+["cash"]:
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
                sql_position_delete = "DELETE FROM my_position  WHERE amount = 0"
                db.execute(sql_position_delete)
                sql_bars = "select * from stock_info a where a.state_dt = '%s' and a.stock_code = '%s'" % (
                    state_dt_1, i)
                done_set_buy = db.select(sql_bars)
                if len(done_set_buy) == 0:
                    print("缺少持仓股票  "+str(i)+"   "+str(state_dt_1)+"  行情数据")
                    opdate2 = (datetime.strptime(state_dt_1, "%Y-%m-%d")).strftime('%Y%m%d')
                    resu = self.pro.daily(ts_code=i, trade_date = opdate2)

                    if len(resu) != 0:
                        print("已经从互联网获取"+str(i)+"   "+str(state_dt_1)+"  行情数据")
                        new_price = resu["close"][0]
                        pct_change = resu["pct_chg"][0]/100+1
                        sql_insert = "INSERT IGNORE INTO stock_all(state_dt,stock_code,open,close,high,low,vol,amount,pre_close,amt_change,pct_change) VALUES ('%s', '%s', '%.2f', '%.2f','%.2f','%.2f','%i','%.2f','%.2f','%.2f','%.2f')" % (
                            state_dt_1, str(resu.iloc[0][0]), float(resu.iloc[0][2]), float(resu.iloc[0][5]),
                            float(resu.iloc[0][3]), float(resu.iloc[0][4]),
                            float(resu.iloc[0][9]), float(resu.iloc[0][10]), float(resu.iloc[0][6]),
                            float(resu.iloc[0][7]), float(resu.iloc[0][8]))
                        db.execute(sql_insert)
                    else:
                        print(str(i) + '  停牌')
                        new_price = deal_daily.stock_amount[i]/deal_daily.stock_volume[i]
                        pct_change = 1

                else:
                    pct_change = done_set_buy[0][10] / 100 + 1
                    new_price = done_set_buy[0][3]

                new_trdate = state_dt
                new_amount = pct_change*deal_daily.stock_amount[i]
                new_cost_price = deal_daily.stock_cost_price[i]
                new_revenue = (pct_change-1)*deal_daily.stock_amount[i] + deal_daily.stock_revenue[i]
                new_margin = deal_daily.stock_margin[i]
                new_side = deal_daily.stock_side[i]
                new_volume = new_amount/new_price
                new_holding_value = float(new_holding_value) + float(new_amount)
                sql_insert = "insert into my_position(trdate,code,cost_price,revenue,volume,amount,margin,side)" \
                             " VALUES ('%s','%s',%.2f,%.2f,%.2f,%.2f,%.2f,'%s')"\
                             % (new_trdate, i, new_cost_price, new_revenue,new_volume, new_amount, new_margin, new_side)
                db.execute(sql_insert)

        # 更新账户表my_capital
        new_available_fund = deal_daily.cur_available_fund  # 现金不变。
        new_capital = float(new_available_fund) + float(new_holding_value)
        new_margin = 0  # 先不填这个坑
        sql_insert = "insert into my_capital(date,available_fund,holding_value,margin,total_asset) " \
                     "VALUES ('%s',%.2f,%.2f,%.2f,%.2f)" \
                     % (state_dt, new_available_fund, new_holding_value, new_margin, new_capital)
        db.execute(sql_insert)
        return 1

    def afterbc(self):
        db = ToMysql()
        sharp,c_std = statistics.get_sharp_rate()
        print('Sharp Rate : ' + str(sharp))
        print('Risk Factor : ' + str(c_std))

        sql_bench_btc = "select * from stock_index a where a.stock_code = '000905.SH' and a.state_dt >= '%s' and a.state_dt <= '%s'" % (
        self.start_date, self.end_date)
        done_set_bench_btc = db.select(sql_bench_btc)
        sql_capital = "select * from my_capital"
        done_set_show_btc = db.select(sql_capital)

        benchmark = [x[3] / done_set_bench_btc[0][3] for x in done_set_bench_btc]
        nav = [x[4] / done_set_show_btc[0][4] for x in done_set_show_btc]
        time = [x[0] for x in done_set_show_btc]
        net = list(map(lambda x: x[0]-x[1]+1, zip(nav, benchmark)))
        data = list(map(list, zip(*[time,nav,benchmark,net])))
        nav_df = pd.DataFrame(data, columns=['time', 'nav', 'benchmark', 'net'])
        nav_df["nav"].astype("float")
        nav_df["benchmark"].astype("float")
        nav_df["net"].astype("float")
        return nav_df
    def bcplot(self,nav_df):
        fig, ax = plt.subplots(1, 1)
        plt.style.use('ggplot')
        plt.plot(nav_df["time"], nav_df['nav'], label='nav')
        plt.plot(nav_df["time"], nav_df['benchmark'], label='benchmark')
        plt.plot(nav_df["time"], nav_df['net'], label='net')
        plt.xlabel('date')
        plt.ylabel('return')
        for label in ax.get_xticklabels():
            label.set_visible(False)
        for label in ax.get_xticklabels()[::20]:
            label.set_visible(True)

        plt.legend()
        plt.show()

if __name__ == '__main__':
    a=main()
    #a.go()
    nav_df = a.afterbc()
    a.bcplot(nav_df)