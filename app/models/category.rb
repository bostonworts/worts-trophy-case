class Category < ApplicationRecord
  validates :bjcp_id, presence: true
  validates :name, presence: true
  validates :year, presence: true
end
