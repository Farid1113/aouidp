"""Add order-level coupon reservations (v0.4)."""
from alembic import op
import sqlalchemy as sa
revision = '8a1d6e2c4b90'
down_revision = '305bacc3fafb'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('discounts',sa.Column('is_coupon_only',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('orders',sa.Column('subtotal',sa.Numeric(12,2),nullable=False,server_default='0.00'))
    op.add_column('orders',sa.Column('coupon_discount',sa.Numeric(12,2),nullable=False,server_default='0.00'))
    op.execute('UPDATE orders SET subtotal = total')
    op.create_table('coupon_redemptions',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('coupon_id',sa.Integer(),sa.ForeignKey('coupons.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('order_id',sa.Integer(),sa.ForeignKey('orders.id',ondelete='CASCADE'),nullable=False,unique=True),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.CheckConstraint("status IN ('reserved','redeemed','released')",name='coupon_redemption_status'),
        sa.CheckConstraint('amount >= 0',name='coupon_redemption_nonnegative'))
    op.create_index('ix_coupon_redemptions_coupon_id','coupon_redemptions',['coupon_id'])

def downgrade():
    op.drop_index('ix_coupon_redemptions_coupon_id',table_name='coupon_redemptions')
    op.drop_table('coupon_redemptions')
    op.drop_column('orders','coupon_discount')
    op.drop_column('orders','subtotal')
    op.drop_column('discounts','is_coupon_only')
