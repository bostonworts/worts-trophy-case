class User < ApplicationRecord
  validates :email, presence: true, uniqueness: { case_sensitive: false }
  validates :full_name, presence: true, uniqueness: true

  passwordless_with :email

  def can_delete?(trophy)
    trophy.user == self
  end

  def deactivated?
    deactivated_at.present?
  end
end
