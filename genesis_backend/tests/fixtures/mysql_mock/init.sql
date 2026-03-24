create table if not exists orders_snapshot (
  id bigint primary key,
  user_id varchar(64) not null,
  created_at datetime not null,
  updated_at datetime not null,
  order_status varchar(32) not null,
  amount decimal(12,2) not null
);

insert into orders_snapshot (id, user_id, created_at, updated_at, order_status, amount)
values
  (1001, 'u_001', '2026-03-20 10:00:00', '2026-03-20 10:05:00', 'PAID', 129.80),
  (1002, 'u_002', '2026-03-20 11:00:00', '2026-03-20 11:03:00', 'PAID', 88.00),
  (1003, 'u_003', '2026-03-21 09:30:00', '2026-03-21 09:35:00', 'REFUNDED', 56.50);

create table if not exists payment_snapshot (
  id bigint primary key,
  order_id bigint not null,
  paid_at datetime not null,
  payment_method varchar(32) not null,
  payment_status varchar(32) not null
);

insert into payment_snapshot (id, order_id, paid_at, payment_method, payment_status)
values
  (9001, 1001, '2026-03-20 10:06:00', 'ALIPAY', 'SUCCESS'),
  (9002, 1002, '2026-03-20 11:04:00', 'WECHAT', 'SUCCESS'),
  (9003, 1003, '2026-03-21 09:36:00', 'CARD', 'REFUNDED');
