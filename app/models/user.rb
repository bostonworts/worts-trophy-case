class User < ApplicationRecord
  validates :email, presence: true, uniqueness: { case_sensitive: false }
  validates :full_name, presence: true, uniqueness: true

  passwordless_with :email

  def can_delete?(trophy)
    owns_trophy?(trophy)
  end

  def can_edit?(trophy)
    owns_trophy?(trophy)
  end

  def deactivated?
    deactivated_at.present?
  end

  private

  def owns_trophy?(trophy)
    trophy.user == self
  end
end
