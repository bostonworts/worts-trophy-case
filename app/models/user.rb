class User < ApplicationRecord
  validates :email, presence: true, uniqueness: { case_sensitive: false }

  passwordless_with :email

  def deactivated?
    deactivated_at.present?
  end
end
